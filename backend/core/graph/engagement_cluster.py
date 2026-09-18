"""Subgraph du cluster Engagement (Content + Social + Email).

Séquentiel puis parallèle : Content génère d'abord (Social/Email ont besoin
du contenu généré pour l'adapter/l'envoyer), puis distribute_to_channels
fanoute vers Social et Email en parallèle une fois le contenu prêt.

Agent Content/Social/Email (backend/agents/content|social|email/) ne sont
pas encore écrits (Prompts 5.3/5.4/5.5) : mêmes replis explicites que
acquisition_cluster.py.
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
    """Voir acquisition_cluster._broadcast_agent_status  même correctif
    (AGENT_STATUS n'était émis par aucun code backend), appliqué ici aux 3
    agents de ce cluster."""
    try:
        from backend.api.websocket.agent_broadcaster import get_agent_broadcaster

        await get_agent_broadcaster().broadcast_agent_status_change(agent, status, client_id=client_id)
    except Exception as exc:
        logger.warning("engagement_cluster.status_broadcast_failed", agent=agent, status=status, error=str(exc))


class EngagementState(MarketingState):
    """Hérite de MarketingState (generated_contents y est déjà défini,
    Annotated[..., operator.add]  pas besoin de le redéclarer) et ajoute les
    champs propres à ce cluster."""

    content_briefs: Optional[list[dict]]
    social_schedule: Optional[list[dict]]
    email_sequences: Optional[list[dict]]
    channel_results: Optional[dict]


async def init_engagement_node(state: EngagementState) -> dict:
    """Construit les briefs de contenu à partir du plan hebdomadaire et de
    l'allocation budgétaire du canal "content" reçus de l'orchestrateur."""
    tasks = (state.get("assigned_tasks") or {}).get("content", [])
    content_briefs = [{"task_id": t.id, "payload": t.payload} for t in tasks] or [
        {"task_id": "default", "payload": {"objective": state["objective"]}}
    ]
    logger.info("engagement_cluster.init", client_id=state["client_id"], brief_count=len(content_briefs))
    return {"content_briefs": content_briefs}


async def run_content_agent_node(state: EngagementState) -> dict:
    client_id = state["client_id"]
    await _broadcast_agent_status("content", "running", client_id)
    try:
        from backend.agents.content.graph import (
            build_content_graph,  # type: ignore[import-not-found]
        )
    except ImportError:
        logger.warning("engagement_cluster.content_agent_not_available")
        await _broadcast_agent_status("content", "error", client_id)
        return {
            "generated_contents": [],
            "completed_agents": ["content"],
            "alerts": [
                Alert(
                    level="warning",
                    source="run_content_agent",
                    message="Agent Content pas encore implémenté (Prompt 5.3)  aucun contenu généré.",
                )
            ],
        }

    graph = build_content_graph()
    result = await graph.ainvoke({"briefs": state.get("content_briefs"), "client_id": client_id})
    await _broadcast_agent_status("content", "idle", client_id)
    return {"generated_contents": result.get("generated_contents", []), "completed_agents": ["content"]}


def _distribute_fanout(state: EngagementState) -> list[Send]:
    """Fanout réel vers Social et Email, une fois le contenu disponible 
    même principe que acquisition_cluster._acquisition_fanout."""
    return [Send("run_social_agent", state), Send("run_email_agent", state)]


async def distribute_to_channels_node(state: EngagementState) -> dict:
    """Répartit les contenus générés selon leur `platform` (voir
    state_models.Content)  prépare le contexte que run_social_agent/
    run_email_agent consommeront, sans effectuer le fanout lui-même (fait
    par l'arête conditionnelle suivante, _distribute_fanout)."""
    contents = state.get("generated_contents") or []
    social_contents = [c for c in contents if c.platform in ("linkedin", "meta", "tiktok")]
    email_contents = [c for c in contents if c.platform == "email"]
    logger.info(
        "engagement_cluster.distribute",
        social_count=len(social_contents),
        email_count=len(email_contents),
    )
    return {"channel_results": {"social_pending": len(social_contents), "email_pending": len(email_contents)}}


async def run_social_agent_node(state: EngagementState) -> dict:
    client_id = state["client_id"]
    await _broadcast_agent_status("social", "running", client_id)
    try:
        from backend.agents.social.graph import (
            build_social_graph,  # type: ignore[import-not-found]
        )
    except ImportError:
        logger.warning("engagement_cluster.social_agent_not_available")
        await _broadcast_agent_status("social", "error", client_id)
        return {
            "published_contents": [],
            "completed_agents": ["social"],
            "alerts": [
                Alert(
                    level="warning",
                    source="run_social_agent",
                    message="Agent Social pas encore implémenté (Prompt 5.4)  aucune publication.",
                )
            ],
        }

    graph = build_social_graph()
    contents = [c for c in (state.get("generated_contents") or []) if c.platform in ("linkedin", "meta", "tiktok")]
    result = await graph.ainvoke({"contents": contents, "client_id": client_id})
    await _broadcast_agent_status("social", "idle", client_id)
    return {"published_contents": result.get("published_contents", []), "completed_agents": ["social"]}


async def run_email_agent_node(state: EngagementState) -> dict:
    client_id = state["client_id"]
    await _broadcast_agent_status("email", "running", client_id)
    try:
        from backend.agents.email.graph import (
            build_email_graph,  # type: ignore[import-not-found]
        )
    except ImportError:
        logger.warning("engagement_cluster.email_agent_not_available")
        await _broadcast_agent_status("email", "error", client_id)
        return {
            "email_sequences_triggered": [],
            "completed_agents": ["email"],
            "alerts": [
                Alert(
                    level="warning",
                    source="run_email_agent",
                    message="Agent Email pas encore implémenté (Prompt 5.5)  aucune séquence déclenchée.",
                )
            ],
        }

    graph = build_email_graph()
    contents = [c for c in (state.get("generated_contents") or []) if c.platform == "email"]
    result = await graph.ainvoke({"contents": contents, "client_id": client_id})
    await _broadcast_agent_status("email", "idle", client_id)
    return {
        "email_sequences_triggered": result.get("email_sequences_triggered", []),
        "completed_agents": ["email"],
    }


async def engagement_reporter_node(state: EngagementState) -> dict:
    logger.info(
        "engagement_cluster.completed",
        generated_contents=len(state.get("generated_contents") or []),
        published_contents=len(state.get("published_contents") or []),
        email_sequences=len(state.get("email_sequences_triggered") or []),
    )
    return {"last_updated_at": datetime.now(timezone.utc)}


def build_engagement_cluster_graph() -> StateGraph:
    builder = StateGraph(EngagementState)

    builder.add_node("init_engagement", init_engagement_node)
    builder.add_node("run_content_agent", run_content_agent_node)
    builder.add_node("distribute_to_channels", distribute_to_channels_node)
    builder.add_node("run_social_agent", run_social_agent_node)
    builder.add_node("run_email_agent", run_email_agent_node)
    builder.add_node("engagement_reporter", engagement_reporter_node)

    builder.add_edge(START, "init_engagement")
    builder.add_edge("init_engagement", "run_content_agent")
    builder.add_edge("run_content_agent", "distribute_to_channels")
    builder.add_conditional_edges(
        "distribute_to_channels", _distribute_fanout, ["run_social_agent", "run_email_agent"]
    )
    builder.add_edge("run_social_agent", "engagement_reporter")
    builder.add_edge("run_email_agent", "engagement_reporter")
    builder.add_edge("engagement_reporter", END)

    return builder.compile()


__all__ = ["EngagementState", "build_engagement_cluster_graph"]
