"""Subgraph du cluster Mesure (Analytics + Reporting). Séquentiel  pas de
fanout, chaque étape dépend du résultat de la précédente.

Agent Analytics/Reporting (backend/agents/analytics|reporting/) et le
service PyTorch de détection d'anomalies (backend/pytorch_models/anomaly/,
Prompt 5.6) ne sont pas encore écrits : mêmes replis explicites que les
deux autres clusters.
"""

from datetime import datetime, timezone
from typing import Optional

import structlog
from langgraph.graph import END, START, StateGraph

from backend.core.state.marketing_state import MarketingState
from backend.core.state.state_models import Alert

logger = structlog.get_logger(__name__)


class MeasureState(MarketingState):
    raw_metrics: Optional[dict]
    analyzed_data: Optional[dict]
    anomalies: Optional[list[dict]]
    report_data: Optional[dict]
    recommendations: Optional[list[str]]


async def collect_all_metrics_node(state: MeasureState) -> dict:
    """Agrège les métriques depuis Matomo + APIs (Google Ads, Meta Ads,
    Mautic...)  clients pas encore écrits (backend/tools/analytics/,
    Prompt 5.6). Repli : dict vide, ne bloque pas le reste du cluster."""
    try:
        from backend.tools.analytics.matomo_client import MatomoClient  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("measure_cluster.matomo_client_not_available")
        return {"raw_metrics": {}, "alerts": [Alert(level="warning", source="collect_all_metrics", message="Client Matomo pas encore implémenté (Prompt 5.6)  métriques non collectées.")]}

    client = MatomoClient()
    raw_metrics = await client.get_visits_summary(site_id=state["client_id"], period="week")
    return {"raw_metrics": raw_metrics}


async def run_analytics_agent_node(state: MeasureState) -> dict:
    try:
        from backend.agents.analytics.graph import build_analytics_graph  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("measure_cluster.analytics_agent_not_available")
        return {
            "analyzed_data": {},
            "analytics_data": {"kpis": {}},
            "completed_agents": ["analytics"],
            "alerts": [
                Alert(
                    level="warning",
                    source="run_analytics_agent",
                    message="Agent Analytics pas encore implémenté (Prompt 5.6)  aucune analyse produite.",
                )
            ],
        }

    graph = build_analytics_graph()
    result = await graph.ainvoke({"raw_metrics": state.get("raw_metrics"), "client_id": state["client_id"]})
    analyzed_data = result.get("analyzed_data", {})
    return {
        "analyzed_data": analyzed_data,
        # Pont vers MarketingState.analytics_data, lu par
        # orchestrator.check_performance_node (clé "kpis").
        "analytics_data": {"kpis": analyzed_data.get("kpis", {})},
        "completed_agents": ["analytics"],
    }


async def detect_anomalies_pytorch_node(state: MeasureState) -> dict:
    """Appelle le service PyTorch d'anomaly detection (même service que
    orchestrator_nodes._detect_anomalies_pytorch, Prompt 5.6  pas encore
    écrit)."""
    try:
        from backend.pytorch_models.anomaly.anomaly_detector import AnomalyDetector  # type: ignore[import-not-found]
    except ImportError:
        logger.debug("measure_cluster.anomaly_detector_not_available")
        return {"anomalies": []}

    try:
        detector = AnomalyDetector()
        kpis = (state.get("analyzed_data") or {}).get("kpis", {})
        result = detector.detect(list(kpis.values()))
        anomalies = [{"score": result.score, "explanation": result.explanation}] if result.is_anomaly else []
        return {"anomalies": anomalies}
    except Exception as exc:
        logger.warning("measure_cluster.anomaly_detection_failed", error=str(exc))
        return {"anomalies": []}


async def run_reporting_agent_node(state: MeasureState) -> dict:
    try:
        from backend.agents.reporting.graph import build_reporting_graph  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("measure_cluster.reporting_agent_not_available")
        return {
            "report_data": {},
            "recommendations": [],
            "completed_agents": ["reporting"],
            "alerts": [
                Alert(
                    level="warning",
                    source="run_reporting_agent",
                    message="Agent Reporting pas encore implémenté  aucun rapport produit.",
                )
            ],
        }

    graph = build_reporting_graph()
    result = await graph.ainvoke(
        {"analyzed_data": state.get("analyzed_data"), "anomalies": state.get("anomalies"), "client_id": state["client_id"]}
    )
    return {
        "report_data": result.get("report_data", {}),
        "recommendations": result.get("recommendations", []),
        "completed_agents": ["reporting"],
    }


async def measure_reporter_node(state: MeasureState) -> dict:
    """Retourne les insights consolidés à l'orchestrateur via
    performance_summary (lu par check_performance_node/generate_report_node)."""
    performance_summary = {
        **(state.get("performance_summary") or {}),
        "report_data": state.get("report_data"),
        "recommendations": state.get("recommendations"),
        "anomaly_count": len(state.get("anomalies") or []),
    }
    logger.info("measure_cluster.completed", anomaly_count=len(state.get("anomalies") or []))
    return {"performance_summary": performance_summary, "last_updated_at": datetime.now(timezone.utc)}


def build_measure_cluster_graph() -> StateGraph:
    builder = StateGraph(MeasureState)

    builder.add_node("collect_all_metrics", collect_all_metrics_node)
    builder.add_node("run_analytics_agent", run_analytics_agent_node)
    builder.add_node("detect_anomalies_pytorch", detect_anomalies_pytorch_node)
    builder.add_node("run_reporting_agent", run_reporting_agent_node)
    builder.add_node("measure_reporter", measure_reporter_node)

    builder.add_edge(START, "collect_all_metrics")
    builder.add_edge("collect_all_metrics", "run_analytics_agent")
    builder.add_edge("run_analytics_agent", "detect_anomalies_pytorch")
    builder.add_edge("detect_anomalies_pytorch", "run_reporting_agent")
    builder.add_edge("run_reporting_agent", "measure_reporter")
    builder.add_edge("measure_reporter", END)

    return builder.compile()


__all__ = ["MeasureState", "build_measure_cluster_graph"]
