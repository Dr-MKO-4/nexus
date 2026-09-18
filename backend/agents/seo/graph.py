"""Graphe LangGraph de l'Agent SEO  séquentiel, pas de fanout interne."""

from langgraph.graph import END, START, StateGraph

from backend.agents.seo.nodes import (
    analyze_competitors_node,
    audit_technical_node,
    generate_briefs_node,
    load_seo_context_node,
    research_keywords_node,
    seo_reporter_node,
    update_seo_memory_node,
)
from backend.agents.seo.state import SEOState


def build_seo_graph() -> StateGraph:
    builder = StateGraph(SEOState)

    builder.add_node("load_seo_context", load_seo_context_node)
    builder.add_node("research_keywords", research_keywords_node)
    builder.add_node("audit_technical", audit_technical_node)
    builder.add_node("analyze_competitors", analyze_competitors_node)
    builder.add_node("generate_briefs", generate_briefs_node)
    builder.add_node("update_seo_memory", update_seo_memory_node)
    builder.add_node("seo_reporter", seo_reporter_node)

    builder.add_edge(START, "load_seo_context")
    builder.add_edge("load_seo_context", "research_keywords")
    builder.add_edge("research_keywords", "audit_technical")
    builder.add_edge("audit_technical", "analyze_competitors")
    builder.add_edge("analyze_competitors", "generate_briefs")
    builder.add_edge("generate_briefs", "update_seo_memory")
    builder.add_edge("update_seo_memory", "seo_reporter")
    builder.add_edge("seo_reporter", END)

    return builder.compile()


__all__ = ["build_seo_graph"]
