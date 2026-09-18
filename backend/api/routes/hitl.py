"""Router validation humaine (HITL)  Prompt 7.1.

Il n'existe pas de table dédiée "HITLRequest" persistée : une validation en
attente EST un `interrupt()` LangGraph suspendu (voir
orchestrator.nodes.hitl_checkpoint_node)  l'identifiant `{id}` de ce router
est donc le `campaign_id` de la campagne PAUSED correspondante (une seule
validation en attente à la fois par campagne, cohérent avec la conception à
un seul `hitl_checkpoint_node` par exécution du graphe). Le payload complet
de la demande (proposition, contexte, options) est reconstruit depuis
`StateSnapshot.tasks[].interrupts[].value`  l'API native de LangGraph pour
retrouver ce qui a été passé à `interrupt()`, pas un champ dupliqué en base.

Chaque action (approve/reject/modify) reprend le thread via
`MainGraph.resume()` (qui appelle `graph.astream(Command(resume=...))`,
l'équivalent async de `graph.update_state()`/`graph.invoke()` cité par le
spec  voir main_graph.py) : réutilise `_resume_campaign_graph`/
`_persist_run_outcome` de routes/campaigns.py plutôt que de dupliquer cette
logique de persistance du résultat.
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from backend.api.auth import get_current_user, get_db_session, require_role
from backend.api.routes.campaigns import _resume_campaign_graph
from backend.db.models.campaigns import Campaign
from backend.db.models.enums import CampaignStatus, UserRole
from backend.db.models.users import User
from backend.db.repositories.campaign_repository import CampaignRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/hitl", tags=["hitl"])

_STRICT = ConfigDict(extra="forbid")
_ACTION_ROLES = (UserRole.ADMIN, UserRole.MANAGER)


class PendingHITL(BaseModel):
    model_config = _STRICT

    campaign_id: UUID
    client_id: UUID
    thread_id: str
    payload: dict[str, Any] | None


class RejectRequest(BaseModel):
    model_config = _STRICT

    comment: str


class ModifyRequest(BaseModel):
    model_config = _STRICT

    modifications: dict[str, Any]


async def _extract_interrupt_payload(main_graph: Any, thread_id: str) -> dict[str, Any] | None:
    history = await main_graph.get_history(thread_id)
    if not history:
        return None
    for task in history[0].tasks:
        for pending_interrupt in getattr(task, "interrupts", ()) or ():
            return pending_interrupt.value
    return None


async def _list_paused_campaigns(session: Any, current_user: User) -> list[Campaign]:
    client_id = None if current_user.role == UserRole.ADMIN else current_user.client_id
    return list(await CampaignRepository(session).get_by_status(CampaignStatus.PAUSED, client_id=client_id))


async def _get_paused_campaign_or_404(session: Any, current_user: User, campaign_id: UUID) -> Campaign:
    campaign = await CampaignRepository(session).get_by_id(campaign_id)
    if campaign is None or campaign.status != CampaignStatus.PAUSED or campaign.thread_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucune validation en attente pour cet identifiant.")
    if current_user.role != UserRole.ADMIN and campaign.client_id != current_user.client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit à ce client.")
    return campaign


@router.get("/pending", response_model=list[PendingHITL])
async def list_pending(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
) -> list[PendingHITL]:
    campaigns = await _list_paused_campaigns(session, current_user)
    main_graph = request.app.state.main_graph
    results: list[PendingHITL] = []
    for campaign in campaigns:
        if campaign.thread_id is None:
            continue
        payload = await _extract_interrupt_payload(main_graph, campaign.thread_id)
        results.append(
            PendingHITL(campaign_id=campaign.id, client_id=campaign.client_id, thread_id=campaign.thread_id, payload=payload)
        )
    return results


@router.get("/{campaign_id}", response_model=PendingHITL)
async def get_pending(
    campaign_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
) -> PendingHITL:
    campaign = await _get_paused_campaign_or_404(session, current_user, campaign_id)
    payload = await _extract_interrupt_payload(request.app.state.main_graph, campaign.thread_id)
    return PendingHITL(campaign_id=campaign.id, client_id=campaign.client_id, thread_id=campaign.thread_id, payload=payload)


async def _resume_with_response(
    campaign_id: UUID, request: Request, session: Any, current_user: User, hitl_response: dict[str, Any]
) -> None:
    import asyncio

    campaign = await _get_paused_campaign_or_404(session, current_user, campaign_id)
    await CampaignRepository(session).update(campaign_id, status=CampaignStatus.ACTIVE)
    asyncio.create_task(_resume_campaign_graph(request.app.state, campaign_id, campaign.thread_id, hitl_response))
    logger.info("hitl.action_dispatched", campaign_id=str(campaign_id), action=hitl_response.get("action"), triggered_by=str(current_user.id))


@router.post("/{campaign_id}/approve", status_code=status.HTTP_202_ACCEPTED)
async def approve(
    campaign_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(require_role(*_ACTION_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> dict[str, str]:
    await _resume_with_response(campaign_id, request, session, current_user, {"action": "resume"})
    return {"status": "resuming"}


@router.post("/{campaign_id}/reject", status_code=status.HTTP_202_ACCEPTED)
async def reject(
    campaign_id: UUID,
    body: RejectRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role(*_ACTION_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> dict[str, str]:
    await _resume_with_response(campaign_id, request, session, current_user, {"action": "stop", "comment": body.comment})
    return {"status": "stopping"}


@router.post("/{campaign_id}/modify", status_code=status.HTTP_202_ACCEPTED)
async def modify(
    campaign_id: UUID,
    body: ModifyRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role(*_ACTION_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> dict[str, str]:
    await _resume_with_response(campaign_id, request, session, current_user, {"action": "modify", "modifications": body.modifications})
    return {"status": "resuming_with_modifications"}


__all__ = ["router"]
