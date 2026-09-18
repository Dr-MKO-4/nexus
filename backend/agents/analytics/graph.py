"""Graphe LangGraph de l'Agent Analytics  séquentiel, pas de fanout interne
(le spec Prompt 5.6 ne décrit aucune arête conditionnelle)."""

from langgraph.graph import END, START, StateGraph

from backend.agents.analytics.nodes import (
    analytics_reporter_node,
    attribution_analysis_node,
    collect_campaign_data_node,
    collect_email_data_node,
    collect_matomo_data_node,
    collect_social_data_node,
    compute_kpis_node,
    detect_anomalies_pytorch_node,
    generate_insights_node,
    store_metrics_node,
)
from backend.agents.analytics.state import AnalyticsState


def build_analytics_graph() -> StateGraph:
    builder = StateGraph(AnalyticsState)

    builder.add_node("collect_matomo_data", collect_matomo_data_node)
    builder.add_node("collect_campaign_data", collect_campaign_data_node)
    builder.add_node("collect_email_data", collect_email_data_node)
    builder.add_node("collect_social_data", collect_social_data_node)
    builder.add_node("compute_kpis", compute_kpis_node)
    builder.add_node("detect_anomalies_pytorch", detect_anomalies_pytorch_node)
    builder.add_node("attribution_analysis", attribution_analysis_node)
    builder.add_node("generate_insights", generate_insights_node)
    builder.add_node("store_metrics", store_metrics_node)
    builder.add_node("analytics_reporter", analytics_reporter_node)

    builder.add_edge(START, "collect_matomo_data")
    builder.add_edge("collect_matomo_data", "collect_campaign_data")
    builder.add_edge("collect_campaign_data", "collect_email_data")
    builder.add_edge("collect_email_data", "collect_social_data")
    builder.add_edge("collect_social_data", "compute_kpis")
    builder.add_edge("compute_kpis", "detect_anomalies_pytorch")
    builder.add_edge("detect_anomalies_pytorch", "attribution_analysis")
    builder.add_edge("attribution_analysis", "generate_insights")
    builder.add_edge("generate_insights", "store_metrics")
    builder.add_edge("store_metrics", "analytics_reporter")
    builder.add_edge("analytics_reporter", END)

    return builder.compile()


__all__ = ["build_analytics_graph"]
