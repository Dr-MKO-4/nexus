"""Handlers WebSocket  Prompt 7.2.

Authentification via token JWT en query param (`?token=...`, spec) : le
protocole WebSocket ne permet pas d'en-tête `Authorization` custom au moment
du handshake dans un navigateur (l'API `WebSocket` du DOM n'expose aucun
moyen d'ajouter des en-têtes)  le query param est la convention standard
pour authentifier un WebSocket côté navigateur, contrairement aux endpoints
SSE de streams.py (où `EventSource`/un simple `fetch` avec un vrai en-tête
`Authorization` reste possible).

Dispatch des actions HITL entrantes : réutilise directement
`routes.campaigns._resume_campaign_graph`/`CampaignRepository` (même logique
que `routes.hitl.py`), plutôt que de dupliquer la logique de reprise du
graphe  la différence est seulement la SOURCE de l'utilisateur authentifié
(payload JWT décodé manuellement ici, pas une dépendance FastAPI `Depends`,
puisqu'un WebSocket n'a qu'UNE authentification au handshake, pas une par
message).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.api.auth import _decode_token
from backend.api.routes.campaigns import _resume_campaign_graph
from backend.api.websocket.connection_manager import ConnectionLimitReached, get_connection_manager
from backend.db.models.enums import CampaignStatus, UserRole
from backend.db.repositories.campaign_repository import CampaignRepository
from backend.db.session import get_session

logger = structlog.get_logger(__name__)

router = APIRouter()

_HITL_ACTIONS = {
    "hitl_approve": {"action": "resume"},
    "hitl_reject": {"action": "stop"},
    "hitl_modify": {"action": "modify"},
}


async def _authenticate(token: str) -> dict[str, Any] | None:
    try:
        return _decode_token(token, expected_type="access")
    except Exception:
        return None


async def _dispatch_hitl_action(app_state: Any, campaign_id_raw: str, token_client_id: str | None, token_role: str, action_key: str, extra: dict) -> dict:
    try:
        campaign_id = UUID(campaign_id_raw)
    except ValueError:
        return {"type": "error", "message": f"campaign_id invalide : {campaign_id_raw!r}."}

    async with get_session() as session:
        campaign = await CampaignRepository(session).get_by_id(campaign_id)
        if campaign is None or campaign.status != CampaignStatus.PAUSED or campaign.thread_id is None:
            return {"type": "error", "message": "Aucune validation en attente pour cette campagne."}
        if token_role != UserRole.ADMIN.value and str(campaign.client_id) != token_client_id:
            return {"type": "error", "message": "Accès interdit à ce client."}

        await CampaignRepository(session).update(campaign_id, status=CampaignStatus.ACTIVE)
        thread_id = campaign.thread_id

    hitl_response = {**_HITL_ACTIONS[action_key], **extra}
    asyncio.create_task(_resume_campaign_graph(app_state, campaign_id, thread_id, hitl_response))
    return {"type": "ack", "campaign_id": str(campaign_id), "action": hitl_response["action"]}


async def _dispatch_incoming(
    message: dict[str, Any], websocket: WebSocket, connection_id: str, token_client_id: str | None, token_role: str
) -> None:
    manager = get_connection_manager()
    message_type = message.get("type")

    if message_type == "pong":
        manager.record_pong(connection_id)
        return

    action = message.get("action")
    if action in _HITL_ACTIONS:
        campaign_id_raw = message.get("campaign_id")
        if not campaign_id_raw:
            await websocket.send_json({"type": "error", "message": "campaign_id manquant."})
            return
        extra = {k: v for k, v in message.items() if k not in ("action", "campaign_id")}
        result = await _dispatch_hitl_action(websocket.app.state, campaign_id_raw, token_client_id, token_role, action, extra)
        await websocket.send_json(result)
        return

    logger.debug("ws_handlers.unknown_message", message=message)
    await websocket.send_json({"type": "error", "message": f"Type de message non reconnu : {message!r}."})


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str, token: str = Query(...)) -> None:
    payload = await _authenticate(token)
    if payload is None:
        await websocket.close(code=4401)
        return

    user_id = payload.get("sub")
    token_client_id = payload.get("client_id")
    token_role = payload.get("role", UserRole.VIEWER.value)
    if token_role != UserRole.ADMIN.value and token_client_id != client_id:
        await websocket.close(code=4403)
        return

    manager = get_connection_manager()
    try:
        connection_id = await manager.connect(websocket, client_id=client_id, user_id=user_id)
    except ConnectionLimitReached:
        logger.warning("ws_handlers.connection_limit_reached", client_id=client_id)
        return

    try:
        while True:
            raw_message = await websocket.receive_json()
            await _dispatch_incoming(raw_message, websocket, connection_id, token_client_id, token_role)
    except WebSocketDisconnect:
        logger.info("ws_handlers.client_disconnected", connection_id=connection_id, client_id=client_id)
    except Exception as exc:
        logger.warning("ws_handlers.receive_loop_error", connection_id=connection_id, error=str(exc))
    finally:
        await manager.disconnect(connection_id)


__all__ = ["router"]
