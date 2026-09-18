"""Router agents  Prompt 7.1.

Pas de registre de processus "agent" persistant dans ce projet (chaque agent
est un sous-graphe LangGraph invoqué à la demande, pas un daemon nommé) :
"statut" est reconstruit à partir de deux sources réelles  la profondeur de
la queue Celery dédiée à l'agent (`task_monitor.get_queue_depths`, Prompt
6.1) et la dernière `AgentDecision` enregistrée pour lui (Prompt 5.x).

Déclenchement manuel (`POST /agents/{name}/trigger`) : chaque agent a une
tâche Celery dédiée avec une signature DIFFÉRENTE (voir
`tasks/workers/{marketing,llm,image}_worker.py`)  pas un `client_id` unique
pour tous. `_AGENT_DISPATCH` documente les kwargs attendus par agent ; le
corps de la requête est passé tel quel à `.delay(**payload)`, une erreur de
kwargs manquants/erronés est renvoyée en 400 (TypeError capturée) plutôt que
de faire échouer silencieusement la tâche Celery après coup.
"""

from typing import Annotated, Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from backend.api.auth import get_current_user, get_db_session, require_role
from backend.db.models.enums import UserRole
from backend.db.models.users import User
from backend.db.repositories.performance_repository import AgentDecisionRepository
from backend.tasks.queues.redis_queue import QUEUE_ANALYTICS, QUEUE_EMAIL, QUEUE_IMAGE, QUEUE_LLM, QUEUE_SEO, QUEUE_SOCIAL
from backend.tasks.queues.task_monitor import get_queue_depths

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

_STRICT = ConfigDict(extra="forbid")


def _dispatch_table() -> dict[str, tuple[Any, str, tuple[str, ...]]]:
    """Import différé (évite de charger tous les modules Celery workers 
    et leurs propres imports d'agents/graphes  au démarrage de l'API pour
    un simple GET /agents, cohérent avec le principe d'imports paresseux déjà
    appliqué ailleurs dans ce projet, ex. orchestrator/nodes.py)."""
    from backend.tasks.workers.llm_worker import generate_content_task, run_agent_task
    from backend.tasks.workers.image_worker import generate_visual_task
    from backend.tasks.workers.marketing_worker import (
        audit_seo_task,
        collect_analytics_task,
        publish_social_post_task,
        send_email_sequence_task,
        update_sea_bids_task,
    )

    return {
        "seo": (audit_seo_task, QUEUE_SEO, ("client_id",)),
        "sea": (update_sea_bids_task, QUEUE_SEO, ("client_id",)),
        "content": (generate_content_task, QUEUE_LLM, ("brief", "client_id")),
        "social": (publish_social_post_task, QUEUE_SOCIAL, ("content_id", "platforms")),
        "email": (send_email_sequence_task, QUEUE_EMAIL, ("contact_ids", "sequence_name")),
        "analytics": (collect_analytics_task, QUEUE_ANALYTICS, ("client_id", "period")),
        "creative": (generate_visual_task, QUEUE_IMAGE, ("brief", "client_id", "campaign_id")),
        # "reporting" : aucune tâche Celery dédiée n'existe (voir
        # llm_worker._AGENT_GRAPH_BUILDERS)  repli sur la tâche générique
        # run_agent_task, exécutée sur QUEUE_LLM comme toute invocation
        # générique, quel que soit l'agent demandé.
        "reporting": (run_agent_task, QUEUE_LLM, ("state_dict",)),
    }


class AgentStatus(BaseModel):
    model_config = _STRICT

    name: str
    queue: str
    queue_depth: int
    last_decision_at: str | None
    expected_trigger_kwargs: list[str]


class TriggerResponse(BaseModel):
    model_config = _STRICT

    task_id: str
    agent_name: str
    queue: str


async def _build_agent_status(agent_name: str, queue: str, expected_kwargs: tuple[str, ...], depths: dict[str, int], session: Any) -> AgentStatus:
    recent = await AgentDecisionRepository(session).list_recent_by_agent(agent_name, limit=1)
    return AgentStatus(
        name=agent_name,
        queue=queue,
        queue_depth=depths.get(queue, -1),
        last_decision_at=recent[0].created_at.isoformat() if recent else None,
        expected_trigger_kwargs=list(expected_kwargs),
    )


@router.get("", response_model=list[AgentStatus])
async def list_agents(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
) -> list[AgentStatus]:
    dispatch = _dispatch_table()
    depths = await get_queue_depths()
    return [await _build_agent_status(name, queue, kwargs, depths, session) for name, (_, queue, kwargs) in dispatch.items()]


@router.get("/{agent_name}/status", response_model=AgentStatus)
async def get_agent_status(
    agent_name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
) -> AgentStatus:
    dispatch = _dispatch_table()
    entry = dispatch.get(agent_name)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent inconnu : {agent_name!r}. Valides : {sorted(dispatch)}")
    _, queue, kwargs = entry
    depths = await get_queue_depths()
    return await _build_agent_status(agent_name, queue, kwargs, depths, session)


@router.post("/{agent_name}/trigger", response_model=TriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_agent(
    agent_name: str,
    payload: dict[str, Any],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.MANAGER))],
) -> TriggerResponse:
    dispatch = _dispatch_table()
    entry = dispatch.get(agent_name)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent inconnu : {agent_name!r}. Valides : {sorted(dispatch)}")
    task, queue, expected_kwargs = entry

    call_kwargs = dict(payload)
    if agent_name == "reporting":
        # run_agent_task(agent_name, state_dict, thread_id) : signature
        # positionnelle générique différente des tâches dédiées ci-dessus.
        call_kwargs = {"agent_name": "reporting", "state_dict": payload, "thread_id": str(uuid4())}

    try:
        async_result = task.delay(**call_kwargs)
    except TypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payload invalide pour l'agent {agent_name!r} (attendu : {list(expected_kwargs)}) : {exc}",
        ) from exc

    logger.info("agents.triggered", agent_name=agent_name, task_id=async_result.id, triggered_by=str(current_user.id))
    return TriggerResponse(task_id=async_result.id, agent_name=agent_name, queue=queue)


@router.get("/{agent_name}/logs")
async def get_agent_logs(
    agent_name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
    limit: int = 50,
) -> list[dict[str, Any]]:
    dispatch = _dispatch_table()
    if agent_name not in dispatch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent inconnu : {agent_name!r}. Valides : {sorted(dispatch)}")

    # Pas de scope client ici (VIEWER non-ADMIN verrait les décisions de
    # TOUS les clients) : ce endpoint est un outil d'exploitation interne 
    # restreint aux rôles ADMIN/MANAGER, contrairement à GET /agents (lecture
    # libre pour tout utilisateur authentifié).
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rôle non autorisé pour consulter les logs inter-clients.")

    decisions = await AgentDecisionRepository(session).list_recent_by_agent(agent_name, limit=limit)
    return [
        {
            "id": str(decision.id),
            "client_id": str(decision.client_id),
            "decision_type": decision.decision_type,
            "decision_data": decision.decision_data,
            "outcome": decision.outcome,
            "created_at": decision.created_at.isoformat(),
        }
        for decision in decisions
    ]


__all__ = ["router"]
