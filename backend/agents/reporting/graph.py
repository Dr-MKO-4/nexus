"""Graphe LangGraph de l'Agent Reporting  séquentiel, avec un point HITL
avant l'envoi (hitl_before_send).

Écart d'intégration documenté (pas une omission silencieuse) : `interrupt()`
(utilisé par `hitl_before_send_node`, même mécanisme que
`orchestrator.nodes.hitl_checkpoint_node`) exige que le graphe soit compilé
AVEC un checkpointer  sans lui, `GraphInterrupt` remonte comme une
exception non gérée plutôt que de suspendre proprement l'exécution (vérifié
par le comportement de `core/graph/main_graph.py`, qui compile
`builder.compile(checkpointer=checkpointer)` pour cette même raison).
`build_reporting_graph()` accepte donc un `checkpointer` optionnel, à
fournir par l'appelant pour un usage réel avec validation humaine. Point
d'intégration NON câblé : `core/graph/measure_cluster.py:
run_reporting_agent_node` (déjà existant, hors périmètre du Prompt 5.8, qui
ne liste que les fichiers `backend/agents/reporting/*`) appelle aujourd'hui
`build_reporting_graph()` sans checkpointer et `ainvoke()` sans
`thread_id`  à corriger dans une tâche ultérieure pour que le HITL de ce
graphe fonctionne réellement une fois intégré au cluster Mesure."""

from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.agents.reporting.nodes import (
    deliver_report_node,
    format_report_node,
    generate_channel_breakdown_node,
    generate_executive_summary_node,
    generate_recommendations_node,
    hitl_before_send_node,
    load_report_context_node,
)
from backend.agents.reporting.state import ReportingState


def build_reporting_graph(checkpointer: Any = None) -> StateGraph:
    builder = StateGraph(ReportingState)

    builder.add_node("load_report_context", load_report_context_node)
    builder.add_node("generate_executive_summary", generate_executive_summary_node)
    builder.add_node("generate_channel_breakdown", generate_channel_breakdown_node)
    builder.add_node("generate_recommendations", generate_recommendations_node)
    builder.add_node("format_report", format_report_node)
    builder.add_node("hitl_before_send", hitl_before_send_node)
    builder.add_node("deliver_report", deliver_report_node)

    builder.add_edge(START, "load_report_context")
    builder.add_edge("load_report_context", "generate_executive_summary")
    builder.add_edge("generate_executive_summary", "generate_channel_breakdown")
    builder.add_edge("generate_channel_breakdown", "generate_recommendations")
    builder.add_edge("generate_recommendations", "format_report")
    builder.add_edge("format_report", "hitl_before_send")
    builder.add_edge("hitl_before_send", "deliver_report")
    builder.add_edge("deliver_report", END)

    return builder.compile(checkpointer=checkpointer)


__all__ = ["build_reporting_graph"]
