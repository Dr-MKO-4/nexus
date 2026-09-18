"""Graphe LangGraph de l'Agent Email  séquentiel, pas de fanout interne
(le spec Prompt 5.5 ne décrit aucune arête conditionnelle)."""

from langgraph.graph import END, START, StateGraph

from backend.agents.email.nodes import (
    email_reporter_node,
    generate_email_content_node,
    load_email_context_node,
    optimize_subject_lines_node,
    schedule_send_node,
    segment_audience_node,
    select_sequence_node,
    track_results_node,
    trigger_mautic_node,
)
from backend.agents.email.state import EmailState


def build_email_graph() -> StateGraph:
    builder = StateGraph(EmailState)

    builder.add_node("load_email_context", load_email_context_node)
    builder.add_node("segment_audience", segment_audience_node)
    builder.add_node("select_sequence", select_sequence_node)
    builder.add_node("generate_email_content", generate_email_content_node)
    builder.add_node("optimize_subject_lines", optimize_subject_lines_node)
    builder.add_node("schedule_send", schedule_send_node)
    builder.add_node("trigger_mautic", trigger_mautic_node)
    builder.add_node("track_results", track_results_node)
    builder.add_node("email_reporter", email_reporter_node)

    builder.add_edge(START, "load_email_context")
    builder.add_edge("load_email_context", "segment_audience")
    builder.add_edge("segment_audience", "select_sequence")
    builder.add_edge("select_sequence", "generate_email_content")
    builder.add_edge("generate_email_content", "optimize_subject_lines")
    builder.add_edge("optimize_subject_lines", "schedule_send")
    builder.add_edge("schedule_send", "trigger_mautic")
    builder.add_edge("trigger_mautic", "track_results")
    builder.add_edge("track_results", "email_reporter")
    builder.add_edge("email_reporter", END)

    return builder.compile()


__all__ = ["build_email_graph"]
