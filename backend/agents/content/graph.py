"""Graphe LangGraph de l'Agent Content  boucle Generator-Evaluator.

Voir `nodes.route_after_evaluation` pour la justification détaillée du
câblage retenu entre `evaluate_quality`/`evaluate_seo_score`/`refine_content`
et le tableau d'arêtes conditionnelles du spec (Prompt 5.3), qui ne nomme
littéralement que `finalize_content`/`generate_draft` comme cibles directes
depuis `evaluate_quality`.
"""

from langgraph.graph import END, START, StateGraph

from backend.agents.content.nodes import (
    content_reporter_node,
    evaluate_quality_node,
    evaluate_seo_score_node,
    finalize_content_node,
    generate_draft_node,
    load_content_context_node,
    refine_content_node,
    route_after_evaluation,
    select_template_node,
    store_content_node,
)
from backend.agents.content.state import ContentState


def build_content_graph() -> StateGraph:
    builder = StateGraph(ContentState)

    builder.add_node("load_content_context", load_content_context_node)
    builder.add_node("select_template", select_template_node)
    builder.add_node("generate_draft", generate_draft_node)
    builder.add_node("evaluate_quality", evaluate_quality_node)
    builder.add_node("evaluate_seo_score", evaluate_seo_score_node)
    builder.add_node("refine_content", refine_content_node)
    builder.add_node("finalize_content", finalize_content_node)
    builder.add_node("store_content", store_content_node)
    builder.add_node("content_reporter", content_reporter_node)

    builder.add_edge(START, "load_content_context")
    builder.add_edge("load_content_context", "select_template")
    builder.add_edge("select_template", "generate_draft")
    builder.add_edge("generate_draft", "evaluate_quality")
    builder.add_edge("evaluate_quality", "evaluate_seo_score")

    builder.add_conditional_edges(
        "evaluate_seo_score",
        route_after_evaluation,
        {
            "refine": "refine_content",
            "retry": "generate_draft",
            "finalize_needs_review": "finalize_content",
        },
    )

    builder.add_edge("refine_content", "finalize_content")
    builder.add_edge("finalize_content", "store_content")
    builder.add_edge("store_content", "content_reporter")
    builder.add_edge("content_reporter", END)

    return builder.compile()


__all__ = ["build_content_graph"]
