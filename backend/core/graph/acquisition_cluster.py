"""Subgraph du cluster Acquisition (SEO + SEA).

C'est ICI, pas dans l'orchestrateur, que le fanout SEO+SEA décrit par le
Prompt 4.2 ("fanout_acquisition : Send() vers Agent SEO et Agent SEA en
parallèle") a lieu réellement  voir la note d'architecture dans
backend/agents/orchestrator/nodes.py (fanout_acquisition_node). Ce module ne
dépend d'aucun autre subgraph, uniquement de backend.core.state.

Agent SEO (backend/agents/seo/) et Agent SEA (backend/agents/sea/) ne sont
pas encore écrits (Prompts 5.1/5.2) : run_seo_agent_node/run_sea_agent_node
importent leur subgraph paresseusement et retombent sur un résultat vide +
Alert explicite si absent, pour que ce cluster reste compilable et testable
dès maintenant.
"""

from datetime import datetime, timezone
from typing import Optional

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.core.state.marketing_state import MarketingState
from backend.core.state.state_models import Alert

logger = structlog.get_logger(__name__)


async def _broadcast_agent_status(agent: str, status: str, client_id: str) -> None:
    """AGENT_STATUS n'était émis par AUCUN code backend (constaté lors d'un
    audit frontend/backend)  seul point réaliste où le broadcaster peut
    connaître le statut RÉEL d'un agent précis (pas de fabrication d'état :
    "running" juste avant son subgraph, "idle"/"error" juste après)."""
    try:
        from backend.api.websocket.agent_broadcaster import get_agent_broadcaster

        await get_agent_broadcaster().broadcast_agent_status_change(agent, status, client_id=client_id)
    except Exception as exc:
        logger.warning("acquisition_cluster.status_broadcast_failed", agent=agent, status=status, error=str(exc))


class AcquisitionState(MarketingState):
    """Hérite de tous les champs de MarketingState (nécessaires pour que les
    canaux du subgraph correspondent à ceux du graphe parent  composition de
    subgraphs à schémas différents mais recouvrants, pattern LangGraph
    standard) et ajoute les 3 champs propres à ce cluster."""

    seo_brief: Optional[dict]
    sea_brief: Optional[dict]
    coordination_notes: Optional[str]


async def init_acquisition_node(state: AcquisitionState) -> dict:
    """Initialise les briefs SEO/SEA à partir des inputs reçus de
    l'orchestrateur (objectif, allocation budgétaire par canal)."""
    allocations = state.get("channel_allocations") or {}
    seo_brief = {"objective": state["objective"], "budget": allocations.get("seo", 0.0)}
    sea_brief = {"objective": state["objective"], "budget": allocations.get("sea", 0.0)}
    logger.info("acquisition_cluster.init", client_id=state["client_id"])
    return {"seo_brief": seo_brief, "sea_brief": sea_brief}


def _acquisition_fanout(state: AcquisitionState) -> list[Send]:
    """Le fanout SEO+SEA réel (Send() vers deux nœuds du MÊME graphe,
    possible ici  contrairement au niveau orchestrateur où SEO/SEA ne sont
    pas visibles)."""
    return [Send("run_seo_agent", state), Send("run_sea_agent", state)]


async def run_seo_agent_node(state: AcquisitionState) -> dict:
    client_id = state["client_id"]
    await _broadcast_agent_status("seo", "running", client_id)
    try:
        from backend.agents.seo.graph import (
            build_seo_graph,  # type: ignore[import-not-found]
        )
    except ImportError:
        logger.warning("acquisition_cluster.seo_agent_not_available")
        await _broadcast_agent_status("seo", "error", client_id)
        return {
            "seo_keywords": [],
            "seo_audit_results": None,
            "completed_agents": ["seo"],
            "alerts": [
                Alert(
                    level="warning",
                    source="run_seo_agent",
                    message="Agent SEO pas encore implémenté (Prompt 5.1)  aucun résultat produit.",
                )
            ],
        }

    graph = build_seo_graph()
    result = await graph.ainvoke({"brief": state.get("seo_brief"), "client_id": client_id})
    await _broadcast_agent_status("seo", "idle", client_id)
    return {
        "seo_keywords": result.get("seo_keywords", []),
        "seo_audit_results": result.get("seo_audit_results"),
        "completed_agents": ["seo"],
    }


async def run_sea_agent_node(state: AcquisitionState) -> dict:
    client_id = state["client_id"]
    await _broadcast_agent_status("sea", "running", client_id)
    try:
        from backend.agents.sea.graph import (
            build_sea_graph,  # type: ignore[import-not-found]
        )
    except ImportError:
        logger.warning("acquisition_cluster.sea_agent_not_available")
        await _broadcast_agent_status("sea", "error", client_id)
        return {
            "sea_campaigns": [],
            "completed_agents": ["sea"],
            "alerts": [
                Alert(
                    level="warning",
                    source="run_sea_agent",
                    message="Agent SEA pas encore implémenté (Prompt 5.2)  aucun résultat produit.",
                )
            ],
        }

    graph = build_sea_graph()
    result = await graph.ainvoke({"brief": state.get("sea_brief"), "client_id": client_id})
    await _broadcast_agent_status("sea", "idle", client_id)
    return {"sea_campaigns": result.get("sea_campaigns", []), "completed_agents": ["sea"]}


async def seo_sea_coordinator_node(state: AcquisitionState) -> dict:
    """Détecte les chevauchements entre mots-clés SEO et ciblage SEA (les
    deux canaux ne devraient pas se cannibaliser sur les mêmes requêtes
    payantes/organiques sans intention délibérée)."""
    seo_terms = {kw.term.lower() for kw in (state.get("seo_keywords") or [])}
    sea_terms: set[str] = set()
    for campaign in state.get("sea_campaigns") or []:
        targeting_keywords = campaign.targeting.get("keywords", []) if isinstance(campaign.targeting, dict) else []
        sea_terms.update(t.lower() for t in targeting_keywords)

    overlap = sorted(seo_terms & sea_terms)
    notes = (
        f"Chevauchement détecté sur {len(overlap)} terme(s) : {', '.join(overlap[:10])}"
        if overlap
        else "Aucun chevauchement SEO/SEA détecté."
    )
    logger.info("acquisition_cluster.coordination", overlap_count=len(overlap))
    return {"coordination_notes": notes}


async def acquisition_reporter_node(state: AcquisitionState) -> dict:
    """Compile les résultats du cluster pour l'orchestrateur  les champs
    SEO/SEA sont déjà dans l'état (reducers appliqués pendant le fanout) ;
    ce nœud ne fait que consigner la fin du cluster."""
    logger.info(
        "acquisition_cluster.completed",
        seo_keywords=len(state.get("seo_keywords") or []),
        sea_campaigns=len(state.get("sea_campaigns") or []),
    )
    return {"last_updated_at": datetime.now(timezone.utc)}


def build_acquisition_cluster_graph() -> StateGraph:
    """Construit et compile le subgraph Acquisition (autonome  pas de
    dépendance sur des nœuds externes, contrairement au graphe de
    l'orchestrateur)."""
    builder = StateGraph(AcquisitionState)

    builder.add_node("init_acquisition", init_acquisition_node)
    builder.add_node("run_seo_agent", run_seo_agent_node)
    builder.add_node("run_sea_agent", run_sea_agent_node)
    builder.add_node("seo_sea_coordinator", seo_sea_coordinator_node)
    builder.add_node("acquisition_reporter", acquisition_reporter_node)

    builder.add_edge(START, "init_acquisition")
    builder.add_conditional_edges("init_acquisition", _acquisition_fanout, ["run_seo_agent", "run_sea_agent"])
    builder.add_edge("run_seo_agent", "seo_sea_coordinator")
    builder.add_edge("run_sea_agent", "seo_sea_coordinator")
    builder.add_edge("seo_sea_coordinator", "acquisition_reporter")
    builder.add_edge("acquisition_reporter", END)

    return builder.compile()


__all__ = ["AcquisitionState", "build_acquisition_cluster_graph"]
