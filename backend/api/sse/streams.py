"""Endpoints SSE  Prompt 7.2.

Authentification via en-tête `Authorization` (spec) : contrairement aux
WebSockets (handlers.py, JWT en query param  le DOM `WebSocket` ne permet
aucun en-tête custom au handshake), une requête SSE reste une requête HTTP
`GET` standard : `EventSource` du navigateur ne permet PAS non plus de fixer
un en-tête `Authorization` (limite connue, documentée par la spec EventSource
elle-même)  mais un `fetch()` avec un lecteur de stream (ou une librairie
cliente dédiée) le peut, et c'est ce que ce module suppose côté client
(cohérent avec la demande explicite du spec, "Authentification via
Authorization header", plutôt que la contrainte réelle d'un `EventSource`
natif). Réutilise directement `Depends(get_current_user)` (Prompt 7.1) :
aucun mécanisme d'auth spécifique aux SSE n'est nécessaire.

`GET /sse/content-stream/{generation_id}` : consommateur d'un canal Redis
Pub/Sub `nexus:sse:content-stream:{generation_id}`, sur lequel un PRODUCTEUR
publierait chaque token au fur et à mesure de sa génération. Ce producteur
N'EXISTE PAS ENCORE dans ce projet : `NexusLLMClient.complete()`
(backend/llm/gateway/llm_client.py, Prompt 3.1) retourne une chaîne complète
une fois la génération terminée, pas un flux token par token publié quelque
part  LiteLLM sait streamer (`stream=True`), mais aucun code de ce projet
ne le fait aujourd'hui ni ne publie de tokens sur ce canal. Endpoint
consommateur implémenté fidèlement (canal réel, format réel), producteur
hors périmètre des fichiers listés par ce prompt : le stream restera vide
(heartbeats seuls) tant que ce producteur n'est pas écrit ailleurs.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from backend.api.auth import get_current_user, get_db_session
from backend.core.memory.redis_client import get_redis_client
from backend.db.models.enums import UserRole
from backend.db.models.users import User
from backend.db.repositories.campaign_repository import CampaignRepository
from backend.db.repositories.performance_repository import AgentDecisionRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/sse", tags=["sse"])

_STREAM_TIMEOUT_SECONDS = 300
_HEARTBEAT_SECONDS = 15
_POLL_INTERVAL_SECONDS = 3


def _authorize_client_access(current_user: User, client_id: str) -> None:
    if current_user.role != UserRole.ADMIN and str(current_user.client_id) != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit à ce client.")


async def _content_stream_generator(generation_id: str) -> AsyncGenerator[dict, None]:
    redis_client = get_redis_client()
    pubsub = redis_client.pubsub()
    channel = f"nexus:sse:content-stream:{generation_id}"
    await pubsub.subscribe(channel)

    start = time.monotonic()
    try:
        while time.monotonic() - start < _STREAM_TIMEOUT_SECONDS:
            raw_message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=_HEARTBEAT_SECONDS)
            if raw_message is None:
                continue  # sse_starlette envoie son propre ping périodique (ping=)
            try:
                token_payload = json.loads(raw_message["data"])
            except (TypeError, ValueError):
                continue
            yield {"data": json.dumps(token_payload)}
            if token_payload.get("done"):
                break
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


@router.get("/content-stream/{generation_id}")
async def content_stream(
    generation_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> EventSourceResponse:
    return EventSourceResponse(_content_stream_generator(generation_id), ping=_HEARTBEAT_SECONDS)


async def _agent_logs_generator(agent_name: str, client_id: str | None) -> AsyncGenerator[dict, None]:
    """Pas de bus d'événements "logs d'agent" dédié (voir agent_broadcaster.py
    pour la même limite côté LangGraph) : ce flux poll périodiquement les
    `AgentDecision` les plus récentes (Prompt 5.x/7.1) plutôt que de
    prétendre pousser des logs en direct qui n'existent nulle part sous
    cette forme."""
    from backend.db.session import get_session

    start = time.monotonic()
    last_seen_id: str | None = None
    while time.monotonic() - start < _STREAM_TIMEOUT_SECONDS:
        async with get_session() as session:
            decisions = await AgentDecisionRepository(session).list_recent_by_agent(
                agent_name, client_id=UUID(client_id) if client_id else None, limit=20
            )
        new_decisions = []
        for decision in decisions:
            if str(decision.id) == last_seen_id:
                break
            new_decisions.append(decision)
        if new_decisions:
            last_seen_id = str(new_decisions[0].id)
            for decision in reversed(new_decisions):
                yield {
                    "data": json.dumps(
                        {
                            "id": str(decision.id),
                            "client_id": str(decision.client_id),
                            "decision_type": decision.decision_type,
                            "decision_data": decision.decision_data,
                            "created_at": decision.created_at.isoformat(),
                        }
                    )
                }
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


@router.get("/agent-logs/{agent_name}")
async def agent_logs(
    agent_name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    client_id: str | None = None,
) -> EventSourceResponse:
    if client_id is not None:
        _authorize_client_access(current_user, client_id)
    elif current_user.role != UserRole.ADMIN:
        # Sans client_id explicite, ce flux couvrirait TOUS les clients 
        # réservé à ADMIN (même restriction que GET /agents/{name}/logs, Prompt 7.1).
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="client_id requis pour ce rôle.")
    return EventSourceResponse(_agent_logs_generator(agent_name, client_id), ping=_HEARTBEAT_SECONDS)


async def _campaign_progress_generator(campaign_id: UUID) -> AsyncGenerator[dict, None]:
    from backend.db.session import get_session

    start = time.monotonic()
    last_snapshot: tuple[str, float] | None = None
    while time.monotonic() - start < _STREAM_TIMEOUT_SECONDS:
        async with get_session() as session:
            campaign = await CampaignRepository(session).get_by_id(campaign_id)
        if campaign is None:
            yield {"data": json.dumps({"error": "Campagne introuvable."})}
            return

        snapshot = (campaign.status.value, float(campaign.budget_consumed))
        if snapshot != last_snapshot:
            last_snapshot = snapshot
            yield {
                "data": json.dumps(
                    {
                        "campaign_id": str(campaign.id),
                        "status": campaign.status.value,
                        "budget_consumed": float(campaign.budget_consumed),
                        "budget_total": float(campaign.budget_total),
                    }
                )
            }
        if campaign.status.value in ("completed", "archived"):
            return
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


@router.get("/campaign-progress/{campaign_id}")
async def campaign_progress(
    campaign_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[object, Depends(get_db_session)],
) -> EventSourceResponse:
    campaign = await CampaignRepository(session).get_by_id(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campagne introuvable.")
    _authorize_client_access(current_user, str(campaign.client_id))
    return EventSourceResponse(_campaign_progress_generator(campaign_id), ping=_HEARTBEAT_SECONDS)


__all__ = ["router"]
