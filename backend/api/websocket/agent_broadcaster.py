"""Diffuseur d'événements agents  Prompt 7.2.

`subscribe_to_langgraph_events()` : LangGraph n'expose PAS de bus
d'événements global cross-run  un `astream()` ne notifie que l'appelant de
CE run précis, il n'existe aucune API "écouter toutes les transitions de
nœuds de tous les graphes en cours" à souscrire depuis l'extérieur. Documenté
honnêtement plutôt que fabriqué : le mécanisme réel de diffusion des
événements d'agents reste ce qu'il était déjà (orchestrator.nodes, Prompt
4.2)  les NŒUDS appellent eux-mêmes les méthodes `broadcast_*` ci-dessous
pendant leur exécution. Cette méthode existe pour satisfaire la forme d'API
demandée par le spec et documenter la limite, pas pour souscrire à quoi que
ce soit.

`subscribe_to_celery_events()` : Celery, à l'inverse, EXPOSE un vrai bus
d'événements (`celery_app.events.Receiver`, la même API que Flower utilise
en interne pour son propre dashboard)  implémentation réelle ci-dessous,
pas un placeholder. `Receiver.capture()` est un appel SYNCHRONE bloquant
(boucle infinie) : exécuté via `asyncio.to_thread`, ce qui impose de
planifier la diffusion asynchrone résultante depuis ce thread séparé via
`asyncio.run_coroutine_threadsafe` (appeler directement une coroutine depuis
un thread sans boucle d'événements propre lève "no running event loop" 
vérifié, pas supposé).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

from backend.api.websocket.connection_manager import ConnectionManager, get_connection_manager
from backend.api.websocket.events import EventType, WebSocketMessage

logger = structlog.get_logger(__name__)

_CELERY_EVENT_TYPES = ("task-sent", "task-started", "task-succeeded", "task-failed", "task-retried")


class AgentBroadcaster:
    def __init__(self, manager: ConnectionManager | None = None) -> None:
        self._manager = manager or get_connection_manager()
        self._celery_capture_connection: Any = None
        self._celery_task: asyncio.Task | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def _message(
        self, event_type: EventType, *, campaign_id: str | None = None, agent_name: str | None = None, payload: dict
    ) -> WebSocketMessage:
        return WebSocketMessage(
            event_type=event_type,
            campaign_id=campaign_id,
            agent_name=agent_name,
            payload=payload,
            timestamp=datetime.now(timezone.utc),
            trace_id=str(uuid4()),
        )

    async def broadcast_agent_status_change(
        self, agent: str, status: str, *, client_id: str | None = None, campaign_id: str | None = None
    ) -> None:
        message = self._message(EventType.AGENT_STATUS, campaign_id=campaign_id, agent_name=agent, payload={"status": status})
        await (self._manager.send_to_client(client_id, message) if client_id else self._manager.broadcast(message))

    async def broadcast_hitl_request(self, hitl_data: dict) -> None:
        """`hitl_data` : le payload passé à `interrupt()` par
        `hitl_checkpoint_node` (voir orchestrator/nodes.py), qui inclut déjà
        `context.client_id`/`context.campaign_id`."""
        context = hitl_data.get("context") or {}
        client_id = hitl_data.get("client_id") or context.get("client_id")
        campaign_id = hitl_data.get("campaign_id") or context.get("campaign_id")
        message = self._message(EventType.HITL_INTERRUPT, campaign_id=campaign_id, payload=hitl_data)
        await (self._manager.send_to_client(client_id, message) if client_id else self._manager.broadcast(message))

    async def broadcast_hitl_resolved(self, client_id: str, campaign_id: str, resolution: dict) -> None:
        message = self._message(EventType.HITL_RESOLVED, campaign_id=campaign_id, payload=resolution)
        await self._manager.send_to_client(client_id, message)

    async def broadcast_budget_update(self, client_id: str, consumed: float, total: float) -> None:
        percentage = (consumed / total * 100) if total else 0.0
        message = self._message(EventType.BUDGET_UPDATE, payload={"consumed": consumed, "total": total, "percentage": percentage})
        await self._manager.send_to_client(client_id, message)

    async def broadcast_campaign_update(self, client_id: str, campaign_id: str, payload: dict) -> None:
        message = self._message(EventType.CAMPAIGN_UPDATE, campaign_id=campaign_id, payload=payload)
        await self._manager.send_to_client(client_id, message)

    async def broadcast_alert(self, payload: dict, *, client_id: str | None = None) -> None:
        message = self._message(EventType.ALERT, payload=payload)
        await (self._manager.send_to_client(client_id, message) if client_id else self._manager.broadcast(message))

    async def broadcast_report_ready(self, client_id: str, report_id: str) -> None:
        message = self._message(EventType.REPORT_READY, payload={"report_id": report_id})
        await self._manager.send_to_client(client_id, message)

    def subscribe_to_langgraph_events(self) -> None:
        """Voir docstring de module  n'y a rien de générique à souscrire ;
        présent pour la forme d'API du spec et pour documenter cette limite
        de LangGraph explicitement plutôt que silencieusement."""
        logger.info("agent_broadcaster.langgraph_events_delegated_to_nodes")

    def subscribe_to_celery_events(self) -> None:
        """Capture les événements des tâches Celery en tâche de fond."""
        self._event_loop = asyncio.get_running_loop()
        self._celery_task = asyncio.create_task(asyncio.to_thread(self._capture_celery_events))
        logger.info("agent_broadcaster.celery_events_subscribed")

    def _on_celery_event(self, event: dict) -> None:
        """Callback SYNCHRONE (contrat de `Receiver`), appelé depuis le
        thread de capture  jamais depuis la boucle asyncio principale."""
        if self._event_loop is None:
            return
        payload = {
            "task_id": event.get("uuid"),
            "task_name": event.get("name"),
            "celery_event_type": event.get("type"),
            "hostname": event.get("hostname"),
        }
        message = self._message(EventType.TASK_PROGRESS, payload=payload)
        asyncio.run_coroutine_threadsafe(self._manager.broadcast(message), self._event_loop)

    def _capture_celery_events(self) -> None:
        from backend.tasks.celery_app import celery_app

        try:
            with celery_app.connection() as connection:
                self._celery_capture_connection = connection
                receiver = celery_app.events.Receiver(
                    connection, handlers={event_type: self._on_celery_event for event_type in _CELERY_EVENT_TYPES}
                )
                receiver.capture(limit=None, timeout=None, wakeup=True)
        except Exception as exc:
            # Fermer `self._celery_capture_connection` depuis `stop_celery_
            # capture()` fait lever cette exception ici (comportement normal
            # d'une connexion fermée pendant `capture()`)  traité comme un
            # arrêt propre, pas une erreur à propager.
            logger.info("agent_broadcaster.celery_capture_stopped", error=str(exc))

    def stop_celery_capture(self) -> None:
        if self._celery_capture_connection is not None:
            try:
                self._celery_capture_connection.release()
            except Exception:
                pass
        if self._celery_task is not None:
            self._celery_task.cancel()


_broadcaster: AgentBroadcaster | None = None


def get_agent_broadcaster() -> AgentBroadcaster:
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = AgentBroadcaster()
    return _broadcaster


__all__ = ["AgentBroadcaster", "get_agent_broadcaster"]
