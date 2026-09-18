"""Graphe LangGraph de l'Agent Creative  séquentiel, pas de fanout interne
(le spec Prompt 5.7 ne décrit aucune arête conditionnelle)."""

from langgraph.graph import END, START, StateGraph

from backend.agents.creative.nodes import (
    creative_reporter_node,
    evaluate_visual_node,
    generate_visual_node,
    post_process_node,
    prepare_comfyui_workflow_node,
    receive_brief_node,
    retrieve_style_references_node,
    select_template_node,
    store_visual_node,
)
from backend.agents.creative.state import CreativeState


def build_creative_graph() -> StateGraph:
    builder = StateGraph(CreativeState)

    builder.add_node("receive_brief", receive_brief_node)
    builder.add_node("select_template", select_template_node)
    builder.add_node("retrieve_style_references", retrieve_style_references_node)
    builder.add_node("prepare_comfyui_workflow", prepare_comfyui_workflow_node)
    builder.add_node("generate_visual", generate_visual_node)
    builder.add_node("evaluate_visual", evaluate_visual_node)
    builder.add_node("post_process", post_process_node)
    builder.add_node("store_visual", store_visual_node)
    builder.add_node("creative_reporter", creative_reporter_node)

    builder.add_edge(START, "receive_brief")
    builder.add_edge("receive_brief", "select_template")
    builder.add_edge("select_template", "retrieve_style_references")
    builder.add_edge("retrieve_style_references", "prepare_comfyui_workflow")
    builder.add_edge("prepare_comfyui_workflow", "generate_visual")
    builder.add_edge("generate_visual", "evaluate_visual")
    builder.add_edge("evaluate_visual", "post_process")
    builder.add_edge("post_process", "store_visual")
    builder.add_edge("store_visual", "creative_reporter")
    builder.add_edge("creative_reporter", END)

    return builder.compile()


__all__ = ["build_creative_graph"]
