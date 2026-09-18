"""Implémentation des nœuds de l'Agent Analytics.

Insights générés avec Llama 3.3 70B (task_type="analytics", voir
hybrid_router.TASK_TYPE_TO_LOCAL_MODEL) via `NexusLLMClient.complete_structured`.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.agents.analytics.kpi_calculator import (
    calculate_cac,
    calculate_cpa,
    calculate_email_roi,
    calculate_organic_traffic_growth,
    calculate_roas,
    multi_touch_attribution,
)
from backend.agents.analytics.prompts import get_analytics_prompt
from backend.agents.analytics.state import AnalyticsState
from backend.llm.gateway.llm_client import NexusLLMClient
from backend.pytorch_models.anomaly.anomaly_detector import AnomalyDetector
from backend.tools.analytics.matomo_client import MatomoClient
from backend.tools.email.mautic_client import MauticClient
from backend.tools.social.n8n_client import WORKFLOW_SOCIAL_METRICS_COLLECT, N8nClient

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


def _json_safe_kpis(kpis: dict) -> dict:
    """`calculate_organic_traffic_growth` retourne légitimement `float('inf')`
    dès qu'il n'existe pas encore de période précédente (le cas de TOUTE
    première exécution pour un client)  `json.dumps` accepte silencieusement
    `inf`/`-inf`/`nan` en Python (extension non standard, `Infinity`/`NaN`
    dans le JSON produit), ce qui peut dérouter un LLM ou un parseur JSON
    strict côté LangFuse. Neutralisé ici juste avant sérialisation pour les
    prompts  la valeur réelle (potentiellement infinie) reste intacte dans
    `state["kpis"]`, stockée telle quelle par store_metrics_node."""
    import math

    safe = {}
    for key, value in kpis.items():
        if isinstance(value, float) and not math.isfinite(value):
            safe[key] = "infini (aucune période précédente disponible)" if value > 0 else "indéfini"
        else:
            safe[key] = value
    return safe


class InsightItem(BaseModel):
    model_config = _STRICT_CONFIG

    summary: str
    priority: str
    supporting_kpi: str = ""


class InsightsResult(BaseModel):
    model_config = _STRICT_CONFIG

    insights: list[InsightItem]


class RecommendationItem(BaseModel):
    model_config = _STRICT_CONFIG

    action: str
    expected_impact: str
    effort: str


class RecommendationsResult(BaseModel):
    model_config = _STRICT_CONFIG

    recommendations: list[RecommendationItem]


class AnomalyExplanation(BaseModel):
    model_config = _STRICT_CONFIG

    explanation: str
    requires_immediate_action: bool


_anomaly_detector: AnomalyDetector | None = None


def _get_anomaly_detector() -> AnomalyDetector:
    global _anomaly_detector
    if _anomaly_detector is None:
        _anomaly_detector = AnomalyDetector.from_checkpoint()
    return _anomaly_detector


async def collect_matomo_data_node(state: AnalyticsState) -> dict:
    """Collecte les données depuis Matomo API. `site_id` : identifiant de
    propriété Matomo par client non encore stocké (backend/db/models/
    clients.py n'a pas ce champ)  repli sur `client_id` lui-même, même
    limite structurelle documentée pour GoogleSearchConsoleClient (Prompt 5.1)."""
    client_id = state["client_id"]
    matomo_data: dict = {}
    try:
        client = MatomoClient()
        try:
            visits_summary = await client.get_visits_summary(client_id, "week", "today")
            traffic_sources = await client.get_traffic_sources(client_id, "week")
            page_performance = await client.get_page_performance(client_id, "week")
            goals_report = await client.get_goals_report(client_id, "week")
            ecommerce_report = await client.get_ecommerce_report(client_id, "week")
            matomo_data = {
                "visits_summary": visits_summary.model_dump(),
                "traffic_sources": traffic_sources.model_dump(),
                "page_performance": [p.model_dump() for p in page_performance],
                "goals_report": goals_report.model_dump(),
                "ecommerce_report": ecommerce_report.model_dump() if ecommerce_report else None,
            }
        finally:
            await client.aclose()
    except RuntimeError as exc:
        logger.warning("analytics_nodes.matomo_unconfigured", client_id=client_id, error=str(exc))
    except Exception as exc:
        logger.warning("analytics_nodes.matomo_collection_failed", client_id=client_id, error=str(exc))

    logger.info("analytics_nodes.matomo_collected", client_id=client_id, has_data=bool(matomo_data))
    return {"matomo_data": matomo_data}


async def collect_campaign_data_node(state: AnalyticsState) -> dict:
    """Collecte les données depuis Google Ads et Meta Ads APIs. Les
    identifiants de compte publicitaire (customer_id/account_id) et les
    tokens par client ne sont pas encore stockés (même limite documentée
    dans agents.sea.nodes.load_sea_context_node)  repli sur un dict vide,
    pas une donnée inventée."""
    client_id = state["client_id"]
    logger.info("analytics_nodes.campaign_data_skipped_no_account_ids", client_id=client_id)
    return {"campaign_data": {}}


async def collect_email_data_node(state: AnalyticsState) -> dict:
    """Collecte les stats depuis Mautic API. Aucune table ne relie
    client_id -> campaign_id Mautic (EmailSequence ne stocke pas l'ID de
    campagne Mautic déclenchée par trigger_mautic_node de l'Agent Email) 
    repli sur un dict vide tant que ce point d'intégration n'est pas câblé."""
    client_id = state["client_id"]
    try:
        MauticClient()  # valide juste que les credentials existent, pour le log
    except RuntimeError as exc:
        logger.warning("analytics_nodes.mautic_unconfigured", client_id=client_id, error=str(exc))
    logger.info("analytics_nodes.email_data_skipped_no_campaign_mapping", client_id=client_id)
    return {"email_data": {}}


async def collect_social_data_node(state: AnalyticsState) -> dict:
    """Collecte les métriques depuis n8n/APIs sociales (workflow
    SOCIAL_METRICS_COLLECT, même mécanique que
    agents.social.nodes.monitor_engagement_node)."""
    client_id = state["client_id"]
    social_data: dict = {}
    n8n = N8nClient()
    try:
        execution = await n8n.trigger_workflow(WORKFLOW_SOCIAL_METRICS_COLLECT, {"client_id": client_id})
        social_data = {"execution_id": execution.execution_id, "status": execution.status}
    except Exception as exc:
        logger.warning("analytics_nodes.social_collection_failed", client_id=client_id, error=str(exc))
    finally:
        await n8n.aclose()

    logger.info("analytics_nodes.social_collected", client_id=client_id, has_data=bool(social_data))
    return {"social_data": social_data}


async def compute_kpis_node(state: AnalyticsState) -> dict:
    """Calcule tous les KPIs cross-canal (kpi_calculator.py) à partir des
    données collectées. Chaque KPI se rabat sur 0.0 (via les guards de
    kpi_calculator) plutôt que d'échouer quand une source est indisponible 
    cohérent avec les replis "dict vide" des nœuds collect_*."""
    client_id = state["client_id"]
    matomo_data = state.get("matomo_data") or {}
    email_data = state.get("email_data") or {}

    visits_summary = matomo_data.get("visits_summary") or {}
    ecommerce_report = matomo_data.get("ecommerce_report") or {}
    goals_report = matomo_data.get("goals_report") or {}

    revenue = float(ecommerce_report.get("revenue", 0.0) or 0.0)
    conversions = float(ecommerce_report.get("nb_conversions", 0) or visits_summary.get("nb_visits_converted", 0) or 0)
    ad_spend = 0.0  # campaign_data vide tant que les comptes pub ne sont pas câblés (voir collect_campaign_data_node)
    email_revenue = float(email_data.get("revenue", 0.0) or 0.0)
    email_costs = float(email_data.get("costs", 0.0) or 0.0)

    current_visits = float(visits_summary.get("nb_visits", 0) or 0)
    previous_visits = await _get_previous_period_visits(client_id)

    kpis = {
        "cac": calculate_cac(ad_spend, conversions),
        "roas": calculate_roas(revenue, ad_spend),
        "cpa": calculate_cpa(ad_spend, conversions),
        "email_roi": calculate_email_roi(email_revenue, email_costs),
        "organic_traffic_growth": calculate_organic_traffic_growth(current_visits, previous_visits),
        "nb_visits": current_visits,
        "nb_conversions": conversions,
        "revenue": revenue,
        "goal_count": float(len(goals_report.get("goals", {}) or {})),
    }

    logger.info("analytics_nodes.kpis_computed", client_id=client_id, kpi_count=len(kpis))
    return {"kpis": kpis}


async def _get_previous_period_visits(client_id: str) -> float:
    """Trafic organique de la période précédente, depuis PostgreSQL
    (PerformanceMetric déjà stockées par un run précédent de store_metrics_node) 
    0.0 si aucun historique (première exécution pour ce client)."""
    try:
        from backend.db.repositories.performance_repository import PerformanceMetricRepository
        from backend.db.session import get_session

        async with get_session() as session:
            metrics = await PerformanceMetricRepository(session).get_by_channel_and_period(
                UUID(client_id),
                "cross_channel",
                datetime.now(timezone.utc) - timedelta(days=14),
                datetime.now(timezone.utc) - timedelta(days=7),
            )
        values = [m.metric_value for m in metrics if m.metric_name == "nb_visits"]
        return values[-1] if values else 0.0
    except Exception as exc:
        logger.debug("analytics_nodes.previous_period_lookup_failed", client_id=client_id, error=str(exc))
        return 0.0


async def detect_anomalies_pytorch_node(state: AnalyticsState) -> dict:
    """Appelle le service PyTorch de détection d'anomalies (AnomalyDetector)
    sur le vecteur de KPIs de la période."""
    client_id = state["client_id"]
    kpis = state.get("kpis") or {}
    detector = _get_anomaly_detector()
    result = detector.detect(list(kpis.values()))
    anomalies = [result.model_dump()] if result.is_anomaly else []
    logger.info("analytics_nodes.anomalies_detected", client_id=client_id, anomaly_count=len(anomalies))
    return {"anomalies": anomalies}


async def attribution_analysis_node(state: AnalyticsState) -> dict:
    """Calcule l'attribution multi-touch (kpi_calculator.multi_touch_attribution).
    Aucune table de parcours de conversion par touchpoint n'existe encore
    (backend/db/models n'a pas ce niveau de détail)  construit des
    touchpoints synthétiques à partir des canaux ayant produit du trafic
    (traffic_sources), limite documentée plutôt qu'un calcul inventé sur des
    données absentes."""
    client_id = state["client_id"]
    kpis = state.get("kpis") or {}
    matomo_data = state.get("matomo_data") or {}
    traffic_sources = matomo_data.get("traffic_sources") or {}

    touchpoints = [{"channel": channel} for channel, count in traffic_sources.items() if count and count > 0]
    conversion_value = float(kpis.get("revenue", 0.0) or 0.0)

    attribution = multi_touch_attribution(touchpoints, conversion_value, algorithm="linear") if touchpoints else {}
    logger.info("analytics_nodes.attribution_computed", client_id=client_id, channel_count=len(attribution))
    return {"attribution": attribution}


async def generate_insights_node(state: AnalyticsState) -> dict:
    """Génère des insights actionnables (INSIGHT_GENERATION_PROMPT), des
    recommandations (RECOMMENDATION_PROMPT), et explique chaque anomalie
    détectée (ANOMALY_EXPLANATION_PROMPT)."""
    client_id = state["client_id"]
    kpis = state.get("kpis") or {}
    kpis_for_prompt = _json_safe_kpis(kpis)
    anomalies = state.get("anomalies") or []
    llm_client = NexusLLMClient()

    insights: list[dict] = []
    try:
        prompt = get_analytics_prompt(
            "analytics-insight-generation",
            kpis=json.dumps(kpis_for_prompt, ensure_ascii=False),
            anomalies=json.dumps(anomalies, ensure_ascii=False),
            contexte_historique="non disponible (première exécution ou historique insuffisant)",
        )
        result = await llm_client.complete_structured(
            prompt=prompt, response_model=InsightsResult, task_type="analytics", client_id=client_id, agent_name="analytics"
        )
        insights = [i.model_dump() for i in result.insights]
    except Exception as exc:
        logger.warning("analytics_nodes.insight_generation_failed", client_id=client_id, error=str(exc))

    recommendations: list[dict] = []
    try:
        prompt = get_analytics_prompt(
            "analytics-recommendation",
            insights=json.dumps(insights, ensure_ascii=False),
            kpis=json.dumps(kpis_for_prompt, ensure_ascii=False),
            budget="non précisé",
        )
        result = await llm_client.complete_structured(
            prompt=prompt, response_model=RecommendationsResult, task_type="analytics", client_id=client_id, agent_name="analytics"
        )
        recommendations = [r.model_dump() for r in result.recommendations]
    except Exception as exc:
        logger.warning("analytics_nodes.recommendation_generation_failed", client_id=client_id, error=str(exc))

    for anomaly in anomalies:
        try:
            prompt = get_analytics_prompt(
                "analytics-anomaly-explanation",
                anomaly=json.dumps(anomaly, ensure_ascii=False),
                kpis=json.dumps(kpis_for_prompt, ensure_ascii=False),
                contexte_historique="non disponible (première exécution ou historique insuffisant)",
            )
            explanation = await llm_client.complete_structured(
                prompt=prompt, response_model=AnomalyExplanation, task_type="analytics", client_id=client_id, agent_name="analytics"
            )
            anomaly["explanation_clear"] = explanation.explanation
            anomaly["requires_immediate_action"] = explanation.requires_immediate_action
        except Exception as exc:
            logger.warning("analytics_nodes.anomaly_explanation_failed", client_id=client_id, error=str(exc))

    logger.info("analytics_nodes.insights_generated", client_id=client_id, insight_count=len(insights), recommendation_count=len(recommendations))
    return {"insights": insights, "recommendations": recommendations, "anomalies": anomalies}


async def store_metrics_node(state: AnalyticsState) -> dict:
    """Sauvegarde les KPIs calculés dans PostgreSQL (PerformanceMetric,
    channel="cross_channel") et les anomalies détectées (AgentDecision,
    decision_type="anomaly_detected")  cette seconde persistance ajoutée au
    Prompt 7.1 : avant ce prompt, `anomalies` ne vivait que dans l'état
    LangGraph du run courant (jamais écrit en base), rendant
    GET /analytics/anomalies irréalisable pour autre chose qu'un run encore
    en mémoire."""
    client_id = state["client_id"]
    kpis = state.get("kpis") or {}
    anomalies = state.get("anomalies") or []
    metrics_stored = False

    if kpis:
        try:
            from backend.db.repositories.performance_repository import PerformanceMetricRepository
            from backend.db.session import get_session

            period_end = datetime.now(timezone.utc)
            period_start = period_end - timedelta(days=7)
            async with get_session() as session:
                repo = PerformanceMetricRepository(session)
                for metric_name, metric_value in kpis.items():
                    await repo.create(
                        client_id=UUID(client_id),
                        channel="cross_channel",
                        metric_name=metric_name,
                        metric_value=float(metric_value),
                        period_start=period_start,
                        period_end=period_end,
                    )
            metrics_stored = True
        except Exception as exc:
            logger.warning("analytics_nodes.store_metrics_failed", client_id=client_id, error=str(exc))

    if anomalies:
        try:
            from backend.db.repositories.performance_repository import AgentDecisionRepository
            from backend.db.session import get_session

            async with get_session() as session:
                repo = AgentDecisionRepository(session)
                for anomaly in anomalies:
                    await repo.create(
                        client_id=UUID(client_id),
                        agent_name="analytics",
                        decision_type="anomaly_detected",
                        decision_data=anomaly,
                    )
        except Exception as exc:
            logger.warning("analytics_nodes.store_anomalies_failed", client_id=client_id, error=str(exc))

    logger.info("analytics_nodes.metrics_stored", client_id=client_id, stored=metrics_stored, kpi_count=len(kpis), anomaly_count=len(anomalies))
    return {"metrics_stored": metrics_stored}


async def analytics_reporter_node(state: AnalyticsState) -> dict:
    """Retourne les résultats à l'orchestrateur/cluster appelant.
    `analyzed_data` reste toujours un dict (jamais None) : measure_cluster.
    run_analytics_agent_node appelle `.get("kpis", {})` dessus sans vérifier
    sa présence au préalable."""
    analyzed_data = {
        "kpis": state.get("kpis") or {},
        "anomalies": state.get("anomalies") or [],
        "attribution": state.get("attribution") or {},
        "insights": state.get("insights") or [],
        "recommendations": state.get("recommendations") or [],
    }
    logger.info("analytics_nodes.completed", client_id=state["client_id"], kpi_count=len(analyzed_data["kpis"]))
    return {"analyzed_data": analyzed_data}
