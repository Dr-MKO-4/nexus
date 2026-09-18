"""Router campaigns  Prompt 7.1.

POST /campaigns lance une exécution du graphe LangGraph de l'Orchestrateur
(MainGraph, backend/core/graph/main_graph.py) en tâche de fond
(`asyncio.create_task`, PAS un worker Celery séparé) : MainGraph détient un
unique checkpointer PostgresSaver ouvert pour toute la durée de vie du
process API (voir main.py: lifespan), déjà accessible via
`request.app.state.main_graph`  ouvrir un second checkpointer par tâche
Celery serait une ressource redondante et plus lourde qu'une simple tâche
asyncio dans la boucle d'événements déjà utilisée par tous les autres
endpoints de ce router.
"""

import asyncio
from datetime import date
from typing import Annotated, Any
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from backend.api.auth import get_current_user, get_db_session, require_role
from backend.core.state.state_manager import serialize_state
from backend.db.models.campaigns import Campaign
from backend.db.models.enums import CampaignStatus, UserRole
from backend.db.models.users import User
from backend.db.repositories.campaign_repository import CampaignRepository
from backend.db.session import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

_STRICT = ConfigDict(extra="forbid")
_MUTATE_ROLES = (UserRole.ADMIN, UserRole.MANAGER)


class CampaignCreate(BaseModel):
    model_config = _STRICT

    client_id: UUID
    name: str
    objective: str
    budget_total: float = Field(gt=0)
    channel_allocations: dict[str, float] | None = None
    start_date: date | None = None
    end_date: date | None = None


class CampaignUpdate(BaseModel):
    model_config = _STRICT

    name: str | None = None
    objective: str | None = None
    budget_total: float | None = Field(default=None, gt=0)
    channel_allocations: dict[str, float] | None = None
    start_date: date | None = None
    end_date: date | None = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: UUID
    client_id: UUID
    name: str
    objective: str
    budget_total: float
    budget_consumed: float
    status: CampaignStatus
    channel_allocations: dict | None
    start_date: date | None
    end_date: date | None
    results: dict | None
    thread_id: str | None


class ResumeRequest(BaseModel):
    model_config = _STRICT

    hitl_response: dict[str, Any] = Field(
        description='Réponse humaine attendue par hitl_checkpoint_node : {"action": "resume"|"stop"|"modify", ...}.'
    )


def _authorize_client_access(current_user: User, client_id: UUID) -> None:
    """VIEWER/MANAGER restreints à leur propre `client_id` ; ADMIN
    (`client_id` NULL, voir db/models/users.py) accède à tous les clients."""
    if current_user.role != UserRole.ADMIN and current_user.client_id != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit à ce client.")


async def _get_campaign_or_404(session, campaign_id: UUID) -> Campaign:
    campaign = await CampaignRepository(session).get_by_id(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campagne introuvable.")
    return campaign


async def _persist_run_outcome(app_state: Any, campaign_id: UUID, thread_id: str, final_state: dict | None) -> None:
    """Commun à `_run_campaign_graph`/`_resume_campaign_graph` : après que le
    flux `astream` s'est arrêté de produire des mises à jour (soit parce que
    le graphe a atteint END, soit parce qu'il a suspendu sur un
    `interrupt()`), interroge l'historique LangGraph pour distinguer les deux
    cas  `StateSnapshot.next` (tuple des prochains nœuds à exécuter) est
    vide seulement si le graphe est réellement terminé, jamais s'il est en
    pause sur un `interrupt()` : un simple flag applicatif comme
    `hitl_required` serait moins fiable (peut rester vrai dans l'état final
    sans qu'aucun interrupt ne soit réellement en attente)."""
    main_graph = app_state.main_graph
    history = await main_graph.get_history(thread_id)
    is_paused = bool(history and history[0].next)

    update_fields: dict[str, Any] = {"status": CampaignStatus.PAUSED if is_paused else CampaignStatus.COMPLETED}
    if final_state is not None:
        update_fields["budget_consumed"] = final_state.get("budget_consumed", 0.0)
        if not is_paused:
            update_fields["results"] = serialize_state(final_state).get("performance_summary")

    async with get_session() as session:
        updated = await CampaignRepository(session).update(campaign_id, **update_fields)
    logger.info(
        "campaigns.graph_run_settled",
        campaign_id=str(campaign_id),
        thread_id=thread_id,
        status=update_fields["status"].value,
    )
    if updated is not None:
        await _notify_campaign_update(updated)


async def _notify_campaign_update(campaign: Campaign) -> None:
    """`CAMPAIGN_UPDATE`/`BUDGET_UPDATE` n'étaient émis par AUCUN code
    backend (constaté par recherche exhaustive lors d'un audit frontend/
    backend)  seul point réaliste où un changement de statut/budget de
    campagne est réellement connu : juste après la mise à jour en base dans
    `_persist_run_outcome` (fin/pause de graphe) ou une mutation explicite
    (update/archive/pause/resume ci-dessous)."""
    try:
        from backend.api.websocket.agent_broadcaster import get_agent_broadcaster

        broadcaster = get_agent_broadcaster()
        client_id = str(campaign.client_id)
        await broadcaster.broadcast_campaign_update(client_id, str(campaign.id), {"status": campaign.status.value})
        await broadcaster.broadcast_budget_update(client_id, campaign.budget_consumed, campaign.budget_total)
    except Exception as exc:
        logger.warning("campaigns.update_notify_failed", campaign_id=str(campaign.id), error=str(exc))


async def _run_campaign_graph(
    app_state: Any,
    campaign_id: UUID,
    thread_id: str,
    objective: str,
    client_id: str,
    budget: float,
    channel_allocations: dict[str, float] | None,
) -> None:
    main_graph = app_state.main_graph
    try:
        final_state: dict | None = None
        async for update in main_graph.run(
            objective,
            client_id,
            budget,
            campaign_id=str(campaign_id),
            channel_allocations=channel_allocations,
            session_id=thread_id,
        ):
            final_state = update
        await _persist_run_outcome(app_state, campaign_id, thread_id, final_state)
    except Exception as exc:
        logger.error("campaigns.graph_run_failed", campaign_id=str(campaign_id), thread_id=thread_id, error=str(exc))
        async with get_session() as session:
            await CampaignRepository(session).update(campaign_id, status=CampaignStatus.PAUSED)


async def _resume_campaign_graph(app_state: Any, campaign_id: UUID, thread_id: str, hitl_response: dict[str, Any]) -> None:
    main_graph = app_state.main_graph
    try:
        final_state: dict | None = None
        async for update in main_graph.resume(thread_id, hitl_response):
            final_state = update
        await _persist_run_outcome(app_state, campaign_id, thread_id, final_state)
        await _notify_hitl_resolved(campaign_id, hitl_response)
    except Exception as exc:
        logger.error("campaigns.graph_resume_failed", campaign_id=str(campaign_id), thread_id=thread_id, error=str(exc))
        async with get_session() as session:
            await CampaignRepository(session).update(campaign_id, status=CampaignStatus.PAUSED)


async def _notify_hitl_resolved(campaign_id: UUID, hitl_response: dict[str, Any]) -> None:
    """`AgentBroadcaster.broadcast_hitl_resolved` (Prompt 7.2) n'était appelé
    NULLE PART dans ce backend jusqu'ici (constaté par recherche exhaustive
    en construisant le frontend, Prompt 8.3)  le bullet spec frontend
    "Après décision : confirmation WebSocket de reprise du workflow"
    (HITLValidation.tsx) était donc irréalisable avec de vraies données.
    Seul point d'appel logique : ICI, juste après qu'une reprise de HITL
    (approve/reject/modify, toujours via `_resume_campaign_graph`) s'est
    réellement terminée  jamais depuis `_run_campaign_graph` (un premier
    lancement de campagne n'est pas une "résolution" de validation)."""
    try:
        from backend.api.websocket.agent_broadcaster import get_agent_broadcaster

        async with get_session() as session:
            campaign = await CampaignRepository(session).get_by_id(campaign_id)
        if campaign is None:
            return
        await get_agent_broadcaster().broadcast_hitl_resolved(str(campaign.client_id), str(campaign_id), hitl_response)
    except Exception as exc:
        logger.warning("campaigns.hitl_resolved_notify_failed", campaign_id=str(campaign_id), error=str(exc))


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    request: Request,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Campaign:
    _authorize_client_access(current_user, body.client_id)

    thread_id = str(uuid4())
    repo = CampaignRepository(session)
    campaign = await repo.create(
        client_id=body.client_id,
        name=body.name,
        objective=body.objective,
        budget_total=body.budget_total,
        budget_consumed=0.0,
        channel_allocations=body.channel_allocations,
        start_date=body.start_date,
        end_date=body.end_date,
        status=CampaignStatus.ACTIVE,
        thread_id=thread_id,
    )

    asyncio.create_task(
        _run_campaign_graph(
            request.app.state,
            campaign.id,
            thread_id,
            body.objective,
            str(body.client_id),
            body.budget_total,
            body.channel_allocations,
        )
    )
    logger.info("campaigns.created", campaign_id=str(campaign.id), client_id=str(body.client_id), thread_id=thread_id)
    return campaign


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    client_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
    limit: int = 100,
    offset: int = 0,
) -> list[Campaign]:
    _authorize_client_access(current_user, client_id)
    return list(await CampaignRepository(session).get_by_client(client_id, limit=limit, offset=offset))


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
) -> Campaign:
    campaign = await _get_campaign_or_404(session, campaign_id)
    _authorize_client_access(current_user, campaign.client_id)
    return campaign


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: UUID,
    body: CampaignUpdate,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Campaign:
    campaign = await _get_campaign_or_404(session, campaign_id)
    _authorize_client_access(current_user, campaign.client_id)

    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return campaign
    updated = await CampaignRepository(session).update(campaign_id, **fields)
    logger.info("campaigns.updated", campaign_id=str(campaign_id), fields=list(fields))
    assert updated is not None  # déjà vérifié par _get_campaign_or_404 ci-dessus
    await _notify_campaign_update(updated)
    return updated


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_campaign(
    campaign_id: UUID,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> None:
    """Archive (soft-delete, status=ARCHIVED)  jamais de suppression
    physique de la ligne : les Content/PerformanceMetric qui référencent
    cette campagne (ON DELETE SET NULL) et son historique LangGraph
    resteraient orphelins ou incohérents autrement."""
    campaign = await _get_campaign_or_404(session, campaign_id)
    _authorize_client_access(current_user, campaign.client_id)
    archived = await CampaignRepository(session).update(campaign_id, status=CampaignStatus.ARCHIVED)
    logger.info("campaigns.archived", campaign_id=str(campaign_id))
    if archived is not None:
        await _notify_campaign_update(archived)


@router.post("/{campaign_id}/pause", response_model=CampaignOut)
async def pause_campaign(
    campaign_id: UUID,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Campaign:
    """Marque la campagne PAUSED en base. Limite honnête : ceci ne coupe PAS
    une tâche `asyncio.create_task` déjà en cours d'exécution pour ce
    thread_id (LangGraph n'expose pas de primitive générique "suspendre
    n'importe quel nœud immédiatement" en dehors des points `interrupt()`
    placés explicitement par le graphe, voir hitl_checkpoint_node)  le
    statut empêche seulement toute REPRISE ultérieure tant qu'il reste à
    PAUSED, l'exécution en cours va à son terme naturel (prochain
    interrupt() ou END)."""
    campaign = await _get_campaign_or_404(session, campaign_id)
    _authorize_client_access(current_user, campaign.client_id)

    if campaign.status != CampaignStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Impossible de mettre en pause une campagne au statut {campaign.status.value!r}.",
        )
    updated = await CampaignRepository(session).update(campaign_id, status=CampaignStatus.PAUSED)
    assert updated is not None
    logger.info("campaigns.paused", campaign_id=str(campaign_id))
    await _notify_campaign_update(updated)
    return updated


@router.post("/{campaign_id}/resume", response_model=CampaignOut)
async def resume_campaign(
    campaign_id: UUID,
    body: ResumeRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Campaign:
    campaign = await _get_campaign_or_404(session, campaign_id)
    _authorize_client_access(current_user, campaign.client_id)

    if campaign.thread_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette campagne n'a jamais été lancée (aucun thread_id).")
    if campaign.status not in (CampaignStatus.PAUSED, CampaignStatus.ACTIVE):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Impossible de reprendre une campagne au statut {campaign.status.value!r}.")

    updated = await CampaignRepository(session).update(campaign_id, status=CampaignStatus.ACTIVE)
    assert updated is not None
    asyncio.create_task(_resume_campaign_graph(request.app.state, campaign_id, campaign.thread_id, body.hitl_response))
    logger.info("campaigns.resume_triggered", campaign_id=str(campaign_id), thread_id=campaign.thread_id, action=body.hitl_response.get("action"))
    await _notify_campaign_update(updated)
    return updated


@router.get("/{campaign_id}/history")
async def get_campaign_history(
    campaign_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
) -> list[dict[str, Any]]:
    """Time-travel LangGraph : chaque checkpoint du thread, le plus récent en
    premier (comportement natif de `MainGraph.get_history`)."""
    campaign = await _get_campaign_or_404(session, campaign_id)
    _authorize_client_access(current_user, campaign.client_id)

    if campaign.thread_id is None:
        return []

    snapshots = await request.app.state.main_graph.get_history(campaign.thread_id)
    return [
        {
            "values": serialize_state(snapshot.values),
            "next": list(snapshot.next),
            "created_at": snapshot.created_at,
        }
        for snapshot in snapshots
    ]


__all__ = ["router"]
