"""Graphe LangGraph de l'Agent SEA  séquentiel, pas de fanout interne."""

from langgraph.graph import END, START, StateGraph

from backend.agents.sea.nodes import (
    analyze_performance_node,
    detect_anomalies_node,
    generate_ad_variants_node,
    load_sea_context_node,
    manage_budget_node,
    optimize_bids_node,
    sea_reporter_node,
)
from backend.agents.sea.state import SEAState


def build_sea_graph() -> StateGraph:
    builder = StateGraph(SEAState)

    builder.add_node("load_sea_context", load_sea_context_node)
    builder.add_node("analyze_performance", analyze_performance_node)
    builder.add_node("optimize_bids", optimize_bids_node)
    builder.add_node("generate_ad_variants", generate_ad_variants_node)
    builder.add_node("manage_budget", manage_budget_node)
    builder.add_node("detect_anomalies", detect_anomalies_node)
    builder.add_node("sea_reporter", sea_reporter_node)

    builder.add_edge(START, "load_sea_context")
    builder.add_edge("load_sea_context", "analyze_performance")
    builder.add_edge("analyze_performance", "optimize_bids")
    builder.add_edge("optimize_bids", "generate_ad_variants")
    builder.add_edge("generate_ad_variants", "manage_budget")
    builder.add_edge("manage_budget", "detect_anomalies")
    builder.add_edge("detect_anomalies", "sea_reporter")
    builder.add_edge("sea_reporter", END)

    return builder.compile()


__all__ = ["build_sea_graph"]
