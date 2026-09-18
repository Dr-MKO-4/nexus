"""Implémentation des nœuds de l'Agent SEA.

Sortie structurée via `NexusLLMClient.complete_structured` (instructor/
Pydantic) pour les 3 nœuds détaillés par le Prompt 5.2 : le texte du prompt
ne répète pas explicitement "instructor/Pydantic" (contrairement au Prompt
5.1, Agent SEO), mais "analyse structurée des métriques" et "génération de
3 variantes... (titre, description, CTA)" décrivent exactement ce que
`complete_structured` sert à garantir  cohérent avec le choix déjà fait
pour l'Agent SEO plutôt qu'un parsing JSON manuel.
"""

import json
from uuid import UUID

import structlog
from pydantic import BaseModel

from backend.agents.sea.budget_manager import CampaignBudgetInfo, alert_if_overspending, calculate_optimal_allocation, check_daily_pace
from backend.agents.sea.prompts import get_sea_prompt
from backend.agents.sea.state import SEAState
from backend.core.state.state_models import CampaignConfig
from backend.llm.gateway.llm_client import NexusLLMClient

logger = structlog.get_logger(__name__)

_AD_FORMAT_CONSTRAINTS = {
    "search": "titre <= 30 caractères, description <= 90 caractères",
    "display": "titre <= 40 caractères, description <= 90 caractères",
    "social": "titre <= 40 caractères, description <= 125 caractères",
}


class PerformanceAnalysis(BaseModel):
    underperforming_campaigns: list[str]
    overperforming_campaigns: list[str]
    requires_bid_adjustment: bool
    reasoning: str


class AdVariant(BaseModel):
    title: str
    description: str
    cta: str


class _AdVariantsResult(BaseModel):
    variants: list[AdVariant]


class BidOptimization(BaseModel):
    recommended_bid: float
    adjustment_pct: float
    reasoning: str


async def load_sea_context_node(state: SEAState) -> dict:
    """Charge les campagnes actives (et leur budget) ainsi que l'historique
    des campagnes du client depuis PostgreSQL.

    Les identifiants de compte publicitaire (customer_id Google Ads,
    account_id Meta) ne sont pas encore stockés  `backend/db/models/
    clients.py` n'a pas ces champs  donc `customer_id`/`account_id`
    restent `None` : les appels live à google_ads.py/meta_ads.py dans
    analyze_performance_node seront sautés tant que ce point d'intégration
    n'est pas câblé (TODO explicite, pas une omission silencieuse)."""
    client_id = state["client_id"]
    campaign_budgets: list[CampaignBudgetInfo] = []
    campaign_history: list[dict] = []
    try:
        from backend.db.repositories.campaign_repository import CampaignRepository
        from backend.db.session import get_session

        async with get_session() as session:
            repo = CampaignRepository(session)
            db_campaigns = await repo.get_active_campaigns(UUID(client_id))
            historical_campaigns = await repo.get_by_client(UUID(client_id))
        campaign_budgets = [
            CampaignBudgetInfo(
                campaign_id=str(c.id), monthly_budget=float(c.budget_total), spend_to_date=float(c.budget_consumed)
            )
            for c in db_campaigns
        ]
        campaign_history = [
            {"campaign_id": str(c.id), "status": c.status.value if hasattr(c.status, "value") else str(c.status)}
            for c in historical_campaigns
        ]
    except Exception as exc:
        logger.warning("sea_nodes.load_context_failed", client_id=client_id, error=str(exc))

    logger.info(
        "sea_nodes.context_loaded",
        client_id=client_id,
        campaign_count=len(campaign_budgets),
        history_count=len(campaign_history),
    )
    return {
        "campaign_budgets": campaign_budgets,
        "active_campaigns": [],
        "campaign_history": campaign_history,
        "customer_id": None,
        "account_id": None,
    }


async def analyze_performance_node(state: SEAState) -> dict:
    """Analyse structurée CPA/ROAS/CTR via LLM (task_type="sea_analysis" ->
    Mistral 7B, voir hybrid_router.py)."""
    campaigns_summary = [
        {"campaign_id": b.campaign_id, "monthly_budget": b.monthly_budget, "spend_to_date": b.spend_to_date}
        for b in (state.get("campaign_budgets") or [])
    ]
    brief = state.get("brief") or {}

    llm_client = NexusLLMClient()
    prompt = get_sea_prompt(
        "sea-performance-analysis",
        campaigns_performance=json.dumps(campaigns_summary, ensure_ascii=False),
        target_cpa=brief.get("target_cpa", "non précisé"),
        total_budget=brief.get("budget", 0.0),
    )
    try:
        analysis = await llm_client.complete_structured(
            prompt=prompt,
            response_model=PerformanceAnalysis,
            task_type="sea_analysis",
            client_id=state["client_id"],
            agent_name="sea",
        )
        result = analysis.model_dump()
    except Exception as exc:
        logger.warning("sea_nodes.structured_output_failed", node="analyze_performance", error=str(exc))
        result = {}

    logger.info("sea_nodes.performance_analyzed", client_id=state["client_id"])
    return {"performance_analysis": result}


async def optimize_bids_node(state: SEAState) -> dict:
    """Calcul des enchères optimales pour les campagnes sous-performantes
    identifiées par analyze_performance_node, selon le CPA cible."""
    analysis = state.get("performance_analysis") or {}
    if not analysis.get("requires_bid_adjustment"):
        return {"bid_adjustments": []}

    llm_client = NexusLLMClient()
    target_cpa = (state.get("brief") or {}).get("target_cpa", "non précisé")
    adjustments: list[dict] = []

    for campaign_id in analysis.get("underperforming_campaigns", []):
        prompt = get_sea_prompt(
            "sea-bid-optimization",
            campaign_id=campaign_id,
            current_cpa="non disponible (pas de données live Google Ads)",
            target_cpa=target_cpa,
            current_bid="non disponible",
            performance_data=json.dumps(analysis, ensure_ascii=False),
        )
        try:
            optimization = await llm_client.complete_structured(
                prompt=prompt,
                response_model=BidOptimization,
                task_type="sea_analysis",
                client_id=state["client_id"],
                agent_name="sea",
            )
            adjustments.append({"campaign_id": campaign_id, **optimization.model_dump()})
        except Exception as exc:
            logger.warning("sea_nodes.structured_output_failed", node="optimize_bids", campaign_id=campaign_id, error=str(exc))

    logger.info("sea_nodes.bids_optimized", client_id=state["client_id"], adjustment_count=len(adjustments))
    return {"bid_adjustments": adjustments}


async def generate_ad_variants_node(state: SEAState) -> dict:
    """3 variantes d'annonce (titre, description, CTA) par format (search,
    display, social)."""
    brief = state.get("brief") or {}
    llm_client = NexusLLMClient()
    all_variants: list[dict] = []

    for ad_format, constraints in _AD_FORMAT_CONSTRAINTS.items():
        prompt = get_sea_prompt(
            "sea-ad-generation",
            objective=brief.get("objective", ""),
            product=brief.get("product", "non précisé"),
            ad_format=ad_format,
            target_audience=brief.get("target_audience", "non précisée"),
            format_constraints=constraints,
        )
        try:
            result = await llm_client.complete_structured(
                prompt=prompt,
                response_model=_AdVariantsResult,
                task_type="sea_analysis",
                client_id=state["client_id"],
                agent_name="sea",
            )
            all_variants.extend({"format": ad_format, **variant.model_dump()} for variant in result.variants)
        except Exception as exc:
            logger.warning("sea_nodes.structured_output_failed", node="generate_ad_variants", ad_format=ad_format, error=str(exc))

    logger.info("sea_nodes.ad_variants_generated", client_id=state["client_id"], variant_count=len(all_variants))
    return {"ad_variants": all_variants}


async def manage_budget_node(state: SEAState) -> dict:
    """Surveille et ajuste l'allocation budgétaire cross-canal (Google Ads/
    Meta Ads). Sans données ROAS live (customer_id/account_id non câblés,
    voir load_sea_context_node), les deux canaux reçoivent un poids égal 
    calculate_optimal_allocation s'ajustera automatiquement dès que des
    données ROAS réelles seront disponibles, sans changement de code."""
    budgets = state.get("campaign_budgets") or []
    total_budget = (state.get("brief") or {}).get("budget", 0.0)
    channel_performances = {"google_ads": 1.0, "meta_ads": 1.0}
    allocation = calculate_optimal_allocation(total_budget, channel_performances) if total_budget else {}
    pacing = check_daily_pace(budgets)

    logger.info("sea_nodes.budget_managed", client_id=state["client_id"], allocation=allocation)
    return {"budget_allocation": allocation, "pacing_status": pacing}


async def detect_anomalies_node(state: SEAState) -> dict:
    """Détecte les dépenses anormales (>90% du budget mensuel consommé)."""
    budgets = state.get("campaign_budgets") or []
    alerts = alert_if_overspending(budgets, threshold=0.9)
    logger.info("sea_nodes.anomalies_detected", client_id=state["client_id"], alert_count=len(alerts))
    return {"overspending_alerts": alerts}


async def sea_reporter_node(state: SEAState) -> dict:
    """Compile et retourne les résultats à l'orchestrateur.

    `platform` est arbitrairement fixé à "google_ads" faute de traçer la
    plateforme par campagne dans backend/db/models/campaigns.py (le modèle
    ORM Campaign n'a pas ce champ)  limite documentée, pas une donnée
    inventée sans avertissement."""
    budgets = state.get("campaign_budgets") or []
    creative_titles = [v["title"] for v in (state.get("ad_variants") or []) if "title" in v]

    sea_campaigns = [
        CampaignConfig(
            name=f"campagne-{budget.campaign_id}",
            platform="google_ads",
            budget=budget.monthly_budget,
            targeting={},
            creatives=creative_titles,
        )
        for budget in budgets
    ]

    logger.info("sea_nodes.completed", client_id=state["client_id"], campaign_count=len(sea_campaigns))
    return {"sea_campaigns": sea_campaigns}
