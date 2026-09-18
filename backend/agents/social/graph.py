"""Graphe LangGraph de l'Agent Social  séquentiel, pas de fanout interne
(le spec Prompt 5.4 ne décrit aucune arête conditionnelle, contrairement à
l'Agent Content)."""

from langgraph.graph import END, START, StateGraph

from backend.agents.social.nodes import (
    adapt_content_per_platform_node,
    crisis_detector_node,
    detect_trends_node,
    load_social_context_node,
    monitor_engagement_node,
    publish_content_node,
    schedule_publications_node,
    sentiment_analysis_node,
    social_reporter_node,
)
from backend.agents.social.state import SocialState


def build_social_graph() -> StateGraph:
    builder = StateGraph(SocialState)

    builder.add_node("load_social_context", load_social_context_node)
    builder.add_node("adapt_content_per_platform", adapt_content_per_platform_node)
    builder.add_node("schedule_publications", schedule_publications_node)
    builder.add_node("publish_content", publish_content_node)
    builder.add_node("monitor_engagement", monitor_engagement_node)
    builder.add_node("detect_trends", detect_trends_node)
    builder.add_node("sentiment_analysis", sentiment_analysis_node)
    builder.add_node("crisis_detector", crisis_detector_node)
    builder.add_node("social_reporter", social_reporter_node)

    builder.add_edge(START, "load_social_context")
    builder.add_edge("load_social_context", "adapt_content_per_platform")
    builder.add_edge("adapt_content_per_platform", "schedule_publications")
    builder.add_edge("schedule_publications", "publish_content")
    builder.add_edge("publish_content", "monitor_engagement")
    builder.add_edge("monitor_engagement", "detect_trends")
    builder.add_edge("detect_trends", "sentiment_analysis")
    builder.add_edge("sentiment_analysis", "crisis_detector")
    builder.add_edge("crisis_detector", "social_reporter")
    builder.add_edge("social_reporter", END)

    return builder.compile()


__all__ = ["build_social_graph"]
