"""Graphe LangGraph de l'Orchestrateur.

`build_orchestrator_graph()` retourne un `StateGraph[MarketingState]` **non
compilé**. Trois de ses arêtes pointent vers des noms de nœuds
("acquisition_cluster", "engagement_cluster", "measure_cluster") qui ne sont
PAS ajoutés ici : ce sont les subgraphs de backend/core/graph/ (Prompt 4.3),
ajoutés par `main_graph.py` (`add_node(name, compiled_subgraph)`) avant
l'appel à `.compile()`. C'est le pattern standard de composition modulaire de
LangGraph  un `StateGraph` peut être construit et étendu en plusieurs
étapes, seule la compilation finale exige que tous les nœuds référencés
existent. Le checkpointer PostgresSaver et la limite de récursion (constantes
ci-dessous) sont donc appliqués dans main_graph.py, pas ici.

INTERRUPT_BEFORE ci-dessous est documentaire seulement  PAS passée à
`compile(interrupt_before=...)` par main_graph.py. hitl_checkpoint_node
appelle déjà `interrupt()` lui-même (mécanisme dynamique) ; combiner les deux
casse la reprise (`Command(resume=...)` échoue avec "Called get_config
outside of a runnable context"  vérifié empiriquement, pas supposé).

Import Send() ciblant "acquisition_cluster"/"engagement_cluster" : voir la
note d'architecture dans nodes.fanout_acquisition_node/fanout_engagement_node
sur pourquoi le fanout SEO+SEA / Content+Social+Email réel a lieu un niveau
plus bas, dans les subgraphs eux-mêmes.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.agents.orchestrator.nodes import (
    check_performance_node,
    consolidate_results_node,
    error_handler_node,
    fanout_acquisition_node,
    fanout_engagement_node,
    generate_report_node,
    handle_crisis_node,
    hitl_checkpoint_node,
    parse_objective_node,
    plan_week_node,
    reallocate_budget_node,
    route_to_cluster_node,
    validate_parallel_results_node,
)
from backend.agents.orchestrator.router import (
    route_after_hitl,
    route_after_performance,
    route_after_plan,
    should_continue_optimization,
    should_validate_hitl,
)
from backend.core.state.marketing_state import MarketingState

# Configuration consommée par main_graph.py au moment de compile()/invoke() 
# centralisée ici comme unique source de vérité (Prompt 4.2, section
# "Configuration").
INTERRUPT_BEFORE = ["hitl_checkpoint"]
RECURSION_LIMIT = 50

# Cluster subgraphs attendus par les arêtes ci-dessous, ajoutés par
# main_graph.py  noms partagés pour éviter toute divergence de frappe.
ACQUISITION_CLUSTER_NODE = "acquisition_cluster"
ENGAGEMENT_CLUSTER_NODE = "engagement_cluster"
MEASURE_CLUSTER_NODE = "measure_cluster"

_CLUSTER_ROUTE_TARGETS = {
    "acquisition": ["fanout_acquisition"],
    "engagement": ["fanout_engagement"],
    "measure": [MEASURE_CLUSTER_NODE],
    "all": ["fanout_acquisition", "fanout_engagement", MEASURE_CLUSTER_NODE],
}


def _route_to_cluster_targets(state: MarketingState) -> list[str]:
    """Traduit la décision de router.route_after_plan (une Literal parmi
    4 valeurs, conforme au Prompt 4.2) en liste de nœuds de destination pour
    add_conditional_edges  LangGraph fanoute nativement vers chaque nœud de
    la liste retournée (pas besoin de Send() ici : ce sont des nœuds
    statiques connus à l'avance, pas un nombre variable d'éléments)."""
    decision = route_after_plan(state)
    return _CLUSTER_ROUTE_TARGETS[decision]


def _fanout_acquisition_send(state: dict) -> list[Send]:
    return [Send(ACQUISITION_CLUSTER_NODE, state)]


def _fanout_engagement_send(state: dict) -> list[Send]:
    return [Send(ENGAGEMENT_CLUSTER_NODE, state)]


def build_orchestrator_graph() -> StateGraph:
    """Construit (sans compiler) le graphe de l'Orchestrateur."""
    builder = StateGraph(MarketingState)

    builder.add_node("parse_objective", parse_objective_node)
    builder.add_node("plan_week", plan_week_node)
    builder.add_node("route_to_cluster", route_to_cluster_node)
    builder.add_node("fanout_acquisition", fanout_acquisition_node)
    builder.add_node("fanout_engagement", fanout_engagement_node)
    builder.add_node("validate_parallel_results", validate_parallel_results_node)
    builder.add_node("consolidate_results", consolidate_results_node)
    builder.add_node("check_performance", check_performance_node)
    builder.add_node("reallocate_budget", reallocate_budget_node)
    builder.add_node("hitl_checkpoint", hitl_checkpoint_node)
    builder.add_node("handle_crisis", handle_crisis_node)
    builder.add_node("generate_report", generate_report_node)
    builder.add_node("error_handler", error_handler_node)

    builder.add_edge(START, "parse_objective")
    builder.add_edge("parse_objective", "plan_week")
    builder.add_edge("plan_week", "route_to_cluster")

    # Après route_to_cluster : vers acquisition, engagement, mesure (ou les
    # trois en parallèle pour "all")  voir _route_to_cluster_targets.
    builder.add_conditional_edges(
        "route_to_cluster",
        _route_to_cluster_targets,
        ["fanout_acquisition", "fanout_engagement", MEASURE_CLUSTER_NODE],
    )

    # fanout_acquisition/fanout_engagement transmettent au subgraph via
    # Send() (un seul destinataire chacun ici ; voir docstring de module).
    builder.add_conditional_edges("fanout_acquisition", _fanout_acquisition_send, [ACQUISITION_CLUSTER_NODE])
    builder.add_conditional_edges("fanout_engagement", _fanout_engagement_send, [ENGAGEMENT_CLUSTER_NODE])

    builder.add_edge(ACQUISITION_CLUSTER_NODE, "validate_parallel_results")
    builder.add_edge(ENGAGEMENT_CLUSTER_NODE, "validate_parallel_results")
    builder.add_edge(MEASURE_CLUSTER_NODE, "validate_parallel_results")

    # Après validate_parallel_results : vers consolidate ou error_handler.
    builder.add_conditional_edges(
        "validate_parallel_results",
        lambda state: "error_handler" if (state.get("errors") or []) else "consolidate_results",
        {"consolidate_results": "consolidate_results", "error_handler": "error_handler"},
    )
    builder.add_edge("error_handler", "consolidate_results")
    builder.add_edge("consolidate_results", "check_performance")

    # Après check_performance : vers reallocate_budget, hitl, ou report.
    builder.add_conditional_edges(
        "check_performance",
        route_after_performance,
        {"reallocate": "reallocate_budget", "hitl": "hitl_checkpoint", "report": "generate_report"},
    )

    # Boucle d'optimisation : reallocate_budget -> check_performance tant que
    # iterations < max_iterations (compteur incrémenté dans reallocate_budget_node).
    builder.add_conditional_edges(
        "reallocate_budget",
        should_continue_optimization,
        {"optimize": "check_performance", "stop": "generate_report"},
    )

    # Après hitl_checkpoint : reprise, arrêt, ou modification selon la
    # réponse humaine (hitl_response, peuplé via Command(resume=...)).
    builder.add_conditional_edges(
        "hitl_checkpoint",
        route_after_hitl,
        {"resume": "reallocate_budget", "modify": "plan_week", "stop": "generate_report"},
    )

    builder.add_edge("handle_crisis", "hitl_checkpoint")
    builder.add_edge("generate_report", END)

    return builder


__all__ = [
    "build_orchestrator_graph",
    "INTERRUPT_BEFORE",
    "RECURSION_LIMIT",
    "ACQUISITION_CLUSTER_NODE",
    "ENGAGEMENT_CLUSTER_NODE",
    "MEASURE_CLUSTER_NODE",
]
