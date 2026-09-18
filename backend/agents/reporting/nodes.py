"""Implémentation des nœuds de l'Agent Reporting.

Résumé exécutif généré avec Qwen3.5 72B (task_type="reporting", voir
hybrid_router.TASK_TYPE_TO_LOCAL_MODEL) via `NexusLLMClient.complete_structured`.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.agents.reporting.prompts import get_reporting_prompt
from backend.agents.reporting.report_builder import build_weekly_report
from backend.agents.reporting.state import ReportingState
from backend.llm.gateway.llm_client import NexusLLMClient

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class ExecutiveSummaryResult(BaseModel):
    model_config = _STRICT_CONFIG

    executive_summary: str


class ChannelSummary(BaseModel):
    model_config = _STRICT_CONFIG

    channel: str
    summary: str


class ChannelBreakdownResult(BaseModel):
    model_config = _STRICT_CONFIG

    channels: list[ChannelSummary]


class RecommendationItem(BaseModel):
    model_config = _STRICT_CONFIG

    action: str
    expected_impact: str
    effort: str = "medium"
    priority: int = Field(default=3, ge=1, le=5)


class RecommendationsResult(BaseModel):
    model_config = _STRICT_CONFIG

    recommendations: list[RecommendationItem]
    next_week_plan: str = ""


async def load_report_context_node(state: ReportingState) -> dict:
    """Charge les données Analytics, les KPIs, les anomalies, les décisions
    de la semaine (PostgreSQL, tous agents confondus)."""
    client_id = state["client_id"]
    analyzed_data = state.get("analyzed_data") or {}
    period = state.get("period") or datetime.now(timezone.utc).strftime("%Y-W%V")
    kpis = analyzed_data.get("kpis") or {}

    decisions: list[dict] = []
    try:
        from backend.db.repositories.performance_repository import AgentDecisionRepository
        from backend.db.session import get_session

        week_start = datetime.now(timezone.utc) - timedelta(days=7)
        async with get_session() as session:
            rows = await AgentDecisionRepository(session).get_by_client(UUID(client_id), since=week_start)
        decisions = [
            {
                "agent_name": r.agent_name,
                "decision_type": r.decision_type,
                "decision_data": r.decision_data,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("reporting_nodes.load_decisions_failed", client_id=client_id, error=str(exc))

    logger.info("reporting_nodes.context_loaded", client_id=client_id, period=period, decision_count=len(decisions))
    return {"kpis": kpis, "decisions": decisions, "period": period}


async def generate_executive_summary_node(state: ReportingState) -> dict:
    """Génère le résumé exécutif en langage naturel avec Qwen3.5 72B."""
    client_id = state["client_id"]
    llm_client = NexusLLMClient()
    try:
        prompt = get_reporting_prompt(
            "reporting-executive-summary",
            period=state.get("period", ""),
            kpis=json.dumps(state.get("kpis") or {}, ensure_ascii=False),
            anomalies=json.dumps((state.get("analyzed_data") or {}).get("anomalies") or [], ensure_ascii=False),
            decisions=json.dumps(
                [{"agent": d.get("agent_name"), "type": d.get("decision_type")} for d in (state.get("decisions") or [])],
                ensure_ascii=False,
            ),
        )
        result = await llm_client.complete_structured(
            prompt=prompt, response_model=ExecutiveSummaryResult, task_type="reporting", client_id=client_id, agent_name="reporting"
        )
        executive_summary = result.executive_summary
    except Exception as exc:
        logger.warning("reporting_nodes.executive_summary_failed", client_id=client_id, error=str(exc))
        executive_summary = "Résumé exécutif indisponible (génération échouée)."

    logger.info("reporting_nodes.executive_summary_generated", client_id=client_id)
    return {"executive_summary": executive_summary}


async def generate_channel_breakdown_node(state: ReportingState) -> dict:
    """Analyse détaillée par canal  s'appuie sur l'attribution multi-touch
    déjà calculée par l'Agent Analytics (`analyzed_data.attribution`, un
    montant de revenu attribué par canal) comme socle chiffré, complété par
    une synthèse qualitative du LLM."""
    client_id = state["client_id"]
    analyzed_data = state.get("analyzed_data") or {}
    attribution = analyzed_data.get("attribution") or {}

    channel_summaries: dict[str, str] = {}
    try:
        prompt = get_reporting_prompt(
            "reporting-channel-analysis",
            channel_kpis=json.dumps(state.get("kpis") or {}, ensure_ascii=False),
            attribution=json.dumps(attribution, ensure_ascii=False),
        )
        result = await llm_client_complete_structured(client_id, prompt, ChannelBreakdownResult)
        channel_summaries = {c.channel: c.summary for c in result.channels}
    except Exception as exc:
        logger.warning("reporting_nodes.channel_breakdown_failed", client_id=client_id, error=str(exc))

    channel_performance = {
        channel: {
            "channel": channel,
            "spend": 0.0,
            "revenue": revenue,
            "roas": 0.0,
            "conversions": 0.0,
            "summary": channel_summaries.get(channel, ""),
        }
        for channel, revenue in attribution.items()
    }

    logger.info("reporting_nodes.channel_breakdown_generated", client_id=client_id, channel_count=len(channel_performance))
    return {"channel_performance": channel_performance}


async def llm_client_complete_structured(client_id: str, prompt: str, response_model: type):
    """Petit helper partagé pour éviter de répéter la construction du client
    LLM dans chaque nœud de ce fichier  même rôle que `NexusLLMClient()`
    instancié localement ailleurs, factorisé ici car plusieurs nœuds de ce
    module l'utilisent de façon identique (task_type/agent_name constants)."""
    llm_client = NexusLLMClient()
    return await llm_client.complete_structured(
        prompt=prompt, response_model=response_model, task_type="reporting", client_id=client_id, agent_name="reporting"
    )


async def generate_recommendations_node(state: ReportingState) -> dict:
    """Recommandations actionnables pour la semaine suivante."""
    client_id = state["client_id"]
    try:
        prompt = get_reporting_prompt(
            "reporting-recommendations",
            executive_summary=state.get("executive_summary", ""),
            channel_breakdown=json.dumps(state.get("channel_performance") or {}, ensure_ascii=False),
            anomalies=json.dumps((state.get("analyzed_data") or {}).get("anomalies") or [], ensure_ascii=False),
        )
        result = await llm_client_complete_structured(client_id, prompt, RecommendationsResult)
        recommendations = [r.model_dump() for r in result.recommendations]
        next_week_plan = result.next_week_plan
    except Exception as exc:
        logger.warning("reporting_nodes.recommendations_failed", client_id=client_id, error=str(exc))
        recommendations = []
        next_week_plan = ""

    logger.info("reporting_nodes.recommendations_generated", client_id=client_id, recommendation_count=len(recommendations))
    return {"recommendations": recommendations, "next_week_plan": next_week_plan}


async def _fetch_top_contents(client_id: str, limit: int = 5) -> list[dict]:
    """Meilleurs contenus de la période, par score d'engagement présent dans
    `Content.performance_data`  non demandé par un nœud dédié du spec,
    rattaché ici (format_report_node) puisque `WeeklyReport.top_contents`
    l'exige."""
    try:
        from backend.db.repositories.content_repository import ContentRepository
        from backend.db.session import get_session

        async with get_session() as session:
            contents = await ContentRepository(session).get_by_client(UUID(client_id), limit=50)
    except Exception as exc:
        logger.warning("reporting_nodes.top_contents_fetch_failed", client_id=client_id, error=str(exc))
        return []

    scored = [
        {
            "content_id": str(c.id),
            "title": c.title,
            "platform": c.platform.value if hasattr(c.platform, "value") else str(c.platform),
            "engagement_score": float((c.performance_data or {}).get("engagement_score", 0.0)),
            "views": int((c.performance_data or {}).get("views", 0)),
        }
        for c in contents
        if c.performance_data
    ]
    scored.sort(key=lambda c: c["engagement_score"], reverse=True)
    return scored[:limit]


async def _fetch_budget_summary(client_id: str) -> dict:
    """Résumé budgétaire cross-campagnes  même remarque que
    `_fetch_top_contents` : requis par `WeeklyReport.budget_summary`, non
    couvert par un nœud dédié du spec."""
    try:
        from backend.db.repositories.campaign_repository import CampaignRepository
        from backend.db.session import get_session

        async with get_session() as session:
            campaigns = await CampaignRepository(session).get_by_client(UUID(client_id))
    except Exception as exc:
        logger.warning("reporting_nodes.budget_summary_fetch_failed", client_id=client_id, error=str(exc))
        return {}

    total_budget = sum(float(c.budget_total) for c in campaigns)
    total_spend = sum(float(c.budget_consumed) for c in campaigns)
    return {
        "total_budget": total_budget,
        "total_spend": total_spend,
        "remaining": total_budget - total_spend,
        "utilization_pct": (total_spend / total_budget * 100) if total_budget else 0.0,
    }


async def format_report_node(state: ReportingState) -> dict:
    """Assemble le rapport final (JSON structuré) via
    report_builder.build_weekly_report."""
    client_id = state["client_id"]
    analyzed_data = {
        **(state.get("analyzed_data") or {}),
        "period": state.get("period"),
        "client_id": client_id,
        "executive_summary": state.get("executive_summary", ""),
        "recommendations": state.get("recommendations") or [],
        "channel_performance": state.get("channel_performance") or {},
        "next_week_plan": state.get("next_week_plan", ""),
        "top_contents": await _fetch_top_contents(client_id),
        "budget_summary": await _fetch_budget_summary(client_id),
    }

    weekly_report = build_weekly_report(analyzed_data, state.get("decisions") or [], state.get("kpis") or {})
    logger.info("reporting_nodes.report_formatted", client_id=client_id, period=weekly_report.period)
    return {"weekly_report": weekly_report.model_dump(mode="json")}


async def hitl_before_send_node(state: ReportingState) -> dict:
    """Validation humaine avant envoi (`interrupt()`, même mécanisme que
    `orchestrator.nodes.hitl_checkpoint_node`). Limite connue et déjà
    documentée ailleurs dans ce projet : `interrupt()` sous LangGraph exige
    Python 3.11+ pour un nœud async (`langgraph/config.py`, garde explicite)
     non exécutable tel quel dans le sandbox de développement (Python
    3.10), mais correct pour les images Docker réelles (python:3.11-slim,
    voir Dockerfile). Suit exactement le même mécanisme que l'orchestrateur,
    pas une réinvention."""
    from langgraph.types import interrupt

    weekly_report = state.get("weekly_report") or {}
    payload = {
        "type": "report_approval",
        "client_id": state["client_id"],
        "period": weekly_report.get("period"),
        "executive_summary": weekly_report.get("executive_summary"),
        "recommendation_count": len(weekly_report.get("recommendations", [])),
    }
    human_response = interrupt(payload)

    approved = bool((human_response or {}).get("approved", False))
    feedback = (human_response or {}).get("feedback")
    logger.info("reporting_nodes.hitl_resolved", client_id=state["client_id"], approved=approved)
    return {"approved": approved, "hitl_feedback": feedback}


async def deliver_report_node(state: ReportingState) -> dict:
    """Envoie le rapport via email et/ou API  seulement si approuvé par
    hitl_before_send_node.

    Dernier nœud du graphe (7 nœuds au total dans le spec, pas de nœud
    "reporter" séparé contrairement aux autres agents) : produit donc AUSSI
    la sortie finale `report_data`/`recommendations`, mêmes noms que
    `MeasureState` (lus par `measure_cluster.run_reporting_agent_node`)."""
    from backend.agents.reporting.delivery import expose_via_api, notify_websocket, send_by_email, store_report

    client_id = state["client_id"]
    weekly_report = state.get("weekly_report") or {}

    if not state.get("approved", False):
        logger.info("reporting_nodes.delivery_skipped_not_approved", client_id=client_id)
        report_data = {**weekly_report, "report_id": None, "report_url": None, "delivered": False}
        return {"report_id": None, "report_url": None, "delivered": False, "report_data": report_data}

    report_id = await store_report(weekly_report, client_id)
    report_with_id = {**weekly_report, "report_id": report_id}
    report_url = await expose_via_api(report_with_id)

    recipient_emails = state.get("recipient_emails") or []
    if recipient_emails:
        await send_by_email(weekly_report, recipient_emails)

    await notify_websocket(report_id, client_id)

    logger.info("reporting_nodes.report_delivered", client_id=client_id, report_id=report_id)
    report_data = {**weekly_report, "report_id": report_id, "report_url": report_url, "delivered": True}
    return {"report_id": report_id, "report_url": report_url, "delivered": True, "report_data": report_data}
