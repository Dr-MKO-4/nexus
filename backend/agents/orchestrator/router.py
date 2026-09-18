"""Fonctions de routage conditionnel du graphe de l'Orchestrateur (graph.py).

Chaque fonction est pure (aucun effet de bord, aucun appel LLM) : elle ne
fait que lire `state` et retourner le nom de l'arête à suivre  c'est la
contrainte que LangGraph impose aux fonctions passées à
`add_conditional_edges`.
"""

from typing import Literal

import structlog

from backend.core.state.marketing_state import MarketingState

logger = structlog.get_logger(__name__)

_ACQUISITION_AGENTS = {"seo", "sea"}
_ENGAGEMENT_AGENTS = {"content", "social", "email"}
_MEASURE_AGENTS = {"analytics", "reporting"}


def should_validate_hitl(state: MarketingState) -> Literal["hitl", "continue"]:
    decision = "hitl" if state.get("hitl_required") else "continue"
    logger.debug("router.should_validate_hitl", decision=decision)
    return decision


def route_after_plan(state: MarketingState) -> Literal["acquisition", "engagement", "measure", "all"]:
    """Route vers le(s) cluster(s) couverts par le plan hebdomadaire
    (weekly_plan). Si plusieurs clusters sont concernés, "all" déclenche les
    trois fanouts (l'Orchestrateur les enchaîne ou les parallélise selon la
    structure du graphe, voir graph.py)."""
    plan = state.get("weekly_plan") or []
    agents_planned = {item.agent for item in plan}

    touches_acquisition = bool(agents_planned & _ACQUISITION_AGENTS)
    touches_engagement = bool(agents_planned & _ENGAGEMENT_AGENTS)
    touches_measure = bool(agents_planned & _MEASURE_AGENTS)

    touched_count = sum([touches_acquisition, touches_engagement, touches_measure])
    if touched_count >= 2:
        decision = "all"
    elif touches_acquisition:
        decision = "acquisition"
    elif touches_engagement:
        decision = "engagement"
    else:
        # Par défaut measure : un plan vide ou ne touchant que analytics/reporting
        # atterrit ici - cohérent avec un cycle d'optimisation qui ne fait que
        # mesurer sans relancer d'acquisition/engagement.
        decision = "measure"

    logger.debug("router.route_after_plan", decision=decision, agents_planned=sorted(agents_planned))
    return decision


def route_after_performance(state: MarketingState) -> Literal["reallocate", "hitl", "report"]:
    """Lit `performance_summary` (écrit par check_performance_node, voir
    nodes.py  même forme que CHECK_PERFORMANCE_PROMPT : requires_reallocation,
    underperforming_channels, overperforming_channels)."""
    summary = state.get("performance_summary") or {}
    requires_reallocation = bool(summary.get("requires_reallocation", False))

    if not requires_reallocation:
        decision = "report"
    elif should_validate_hitl(state) == "hitl":
        decision = "hitl"
    else:
        decision = "reallocate"

    logger.debug("router.route_after_performance", decision=decision, requires_reallocation=requires_reallocation)
    return decision


def route_after_hitl(state: MarketingState) -> Literal["resume", "stop", "modify"]:
    """Lit `hitl_response` (rempli par l'API après une validation humaine 
    voir main_graph.resume(), Prompt 4.3). Une réponse absente ou mal formée
    est traitée comme "stop" : par sécurité, ne jamais reprendre une
    exécution automatiquement sur une réponse ambiguë."""
    response = state.get("hitl_response") or {}
    action = response.get("action")

    decision: Literal["resume", "stop", "modify"] = action if action in ("resume", "stop", "modify") else "stop"
    logger.debug("router.route_after_hitl", decision=decision, raw_action=action)
    return decision


def should_continue_optimization(state: MarketingState) -> Literal["optimize", "stop"]:
    """Boucle d'optimisation : continue tant que iterations < max_iterations.
    Utilisée après reallocate_budget pour revenir à check_performance (voir
    graph.py) sans dépasser la limite d'itérations de l'état."""
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 0)
    decision = "optimize" if iterations < max_iterations else "stop"
    logger.debug("router.should_continue_optimization", decision=decision, iterations=iterations, max_iterations=max_iterations)
    return decision
