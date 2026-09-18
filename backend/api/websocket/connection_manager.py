"""Gestionnaire de connexions WebSocket  Prompt 7.2.

Architecture multi-instance (spec : "stockage des connexions actives dans
Redis") : une connexion WebSocket est un socket TCP vivant, attaché à UN
SEUL process  impossible de la "stocker" littéralement dans Redis (aucun
objet socket ne survit à une sérialisation). Le design réel :
- Chaque instance garde ses PROPRES connexions dans un dict en mémoire
  (`self._connections`), c'est la seule source de vérité pour ENVOYER sur un
  socket donné.
- Redis sert à deux choses : (1) un registre `nexus:ws:conn:{id}` avec TTL
  (rafraîchi à chaque heartbeat), qui permet à `get_active_connections_count()`
  de compter les connexions de TOUTES les instances, pas seulement celle-ci ;
  (2) un canal Pub/Sub (`nexus:ws:events`) sur lequel TOUTES les instances
  publient ET s'abonnent  `send_to_user`/`send_to_client`/`broadcast`
  publient un message enveloppé (scope + cible), chaque instance qui le
  reçoit ne délivre qu'aux connexions qu'elle détient localement et qui
  correspondent à la cible. Un seul chemin de code pour la livraison locale
  ET distante, plutôt que deux implémentations à maintenir en parallèle.

"Reconnexion automatique côté serveur si connexion perdue" (spec) : un
serveur ne peut PAS rappeler un client WebSocket déconnecté (la reconnexion
est par nature initiée par le client, comme tout WebSocket standard)  ce
qui est réellement du ressort du serveur : (1) détecter une connexion morte
via heartbeat (ping/pong) et la nettoyer proprement (sinon un slot zombie
compte indéfiniment dans la limite de 100), pour qu'une NOUVELLE tentative
de connexion du même client soit acceptée immédiatement plutôt que rejetée à
tort ; (2) rendre la boucle de réception par connexion (handlers.py)
résiliente à `WebSocketDisconnect` sans jamais faire planter le gestionnaire
ni les autres connexions. C'est ce qui est implémenté ci-dessous.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import structlog
from fastapi import WebSocket

from backend.api.websocket.events import WebSocketMessage
from backend.core.memory.redis_client import RedisClient, get_redis_client

logger = structlog.get_logger(__name__)

_CHANNEL = "nexus:ws:events"
_REGISTRY_PREFIX = "nexus:ws:conn:"

MAX_CONNECTIONS = 100
HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_TIMEOUT_SECONDS = 60


class ConnectionLimitReached(Exception):
    pass


@dataclass
class _LocalConnection:
    websocket: WebSocket
    client_id: str
    user_id: str
    last_pong: float


class ConnectionManager:
    def __init__(self, redis_client: RedisClient | None = None) -> None:
        self._redis_client = redis_client or get_redis_client()
        self._connections: dict[str, _LocalConnection] = {}
        self._instance_id = str(uuid4())
        self._subscriber_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None

    @staticmethod
    def _registry_key(connection_id: str) -> str:
        return f"{_REGISTRY_PREFIX}{connection_id}"

    async def start(self) -> None:
        """À appeler une fois au démarrage de l'API (lifespan)  lance les
        deux boucles de fond (abonnement Pub/Sub + heartbeat)."""
        self._subscriber_task = asyncio.create_task(self._subscriber_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("connection_manager.started", instance_id=self._instance_id)

    async def stop(self) -> None:
        for task in (self._subscriber_task, self._heartbeat_task):
            if task is not None:
                task.cancel()
        for connection_id in list(self._connections):
            await self.disconnect(connection_id)
        logger.info("connection_manager.stopped", instance_id=self._instance_id)

    async def connect(self, websocket: WebSocket, client_id: str, user_id: str) -> str:
        active_count = await self.get_active_connections_count()
        if active_count >= MAX_CONNECTIONS:
            # 1013 = "Try Again Later", code de fermeture WebSocket standard
            # (RFC 6455 §7.4.1 / registre IANA) pour un refus de capacité.
            await websocket.close(code=1013)
            raise ConnectionLimitReached(f"Limite de {MAX_CONNECTIONS} connexions simultanées atteinte.")

        await websocket.accept()
        connection_id = str(uuid4())
        self._connections[connection_id] = _LocalConnection(
            websocket=websocket, client_id=client_id, user_id=user_id, last_pong=time.monotonic()
        )
        await self._refresh_registry(connection_id, client_id, user_id)
        logger.info("connection_manager.connected", connection_id=connection_id, client_id=client_id, user_id=user_id)
        return connection_id

    async def _refresh_registry(self, connection_id: str, client_id: str, user_id: str) -> None:
        payload = json.dumps({"client_id": client_id, "user_id": user_id, "instance_id": self._instance_id})
        await self._redis_client.set(self._registry_key(connection_id), payload, ttl=HEARTBEAT_TIMEOUT_SECONDS)

    async def disconnect(self, connection_id: str) -> None:
        connection = self._connections.pop(connection_id, None)
        await self._redis_client.delete(self._registry_key(connection_id))
        if connection is not None:
            try:
                await connection.websocket.close()
            except Exception:
                pass
            logger.info("connection_manager.disconnected", connection_id=connection_id)

    def record_pong(self, connection_id: str) -> None:
        """Appelé par handlers.py à chaque frame `{"type": "pong"}` reçue."""
        connection = self._connections.get(connection_id)
        if connection is not None:
            connection.last_pong = time.monotonic()

    async def _publish(self, scope: str, target: str | None, message: WebSocketMessage) -> None:
        envelope = {"scope": scope, "target": target, "message": message.model_dump(mode="json")}
        await self._redis_client.publish(_CHANNEL, json.dumps(envelope, default=str))

    async def send_to_user(self, user_id: str, message: WebSocketMessage) -> None:
        await self._publish("user", user_id, message)

    async def send_to_client(self, client_id: str, message: WebSocketMessage) -> None:
        await self._publish("client", client_id, message)

    async def broadcast(self, message: WebSocketMessage) -> None:
        await self._publish("all", None, message)

    async def get_active_connections_count(self) -> int:
        """Compte GLOBAL (toutes instances)  via le registre Redis, pas
        `len(self._connections)` qui ne verrait que cette instance."""
        keys = await self._redis_client.scan_keys(f"{_REGISTRY_PREFIX}*")
        return len(keys)

    async def _deliver_locally(self, envelope: dict) -> None:
        scope, target, message = envelope["scope"], envelope.get("target"), envelope["message"]
        for connection_id, connection in list(self._connections.items()):
            matches = scope == "all" or (scope == "user" and connection.user_id == target) or (
                scope == "client" and connection.client_id == target
            )
            if not matches:
                continue
            try:
                await connection.websocket.send_json(message)
            except Exception as exc:
                logger.warning("connection_manager.send_failed_disconnecting", connection_id=connection_id, error=str(exc))
                await self.disconnect(connection_id)

    async def _subscriber_loop(self) -> None:
        pubsub = self._redis_client.pubsub()
        await pubsub.subscribe(_CHANNEL)
        logger.info("connection_manager.subscriber_started", instance_id=self._instance_id)
        try:
            async for raw_message in pubsub.listen():
                if raw_message.get("type") != "message":
                    continue
                try:
                    envelope = json.loads(raw_message["data"])
                except (TypeError, ValueError) as exc:
                    logger.warning("connection_manager.malformed_envelope", error=str(exc))
                    continue
                await self._deliver_locally(envelope)
        except asyncio.CancelledError:
            raise
        finally:
            await pubsub.unsubscribe(_CHANNEL)
            await pubsub.close()

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                now = time.monotonic()
                for connection_id, connection in list(self._connections.items()):
                    if now - connection.last_pong > HEARTBEAT_TIMEOUT_SECONDS:
                        logger.warning("connection_manager.heartbeat_timeout", connection_id=connection_id)
                        await self.disconnect(connection_id)
                        continue
                    try:
                        await connection.websocket.send_json({"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()})
                        # Rafraîchit le TTL du registre Redis à chaque ping
                        # envoyé  sinon l'entrée expirerait au bout de
                        # HEARTBEAT_TIMEOUT_SECONDS même pour une connexion
                        # parfaitement vivante.
                        await self._refresh_registry(connection_id, connection.client_id, connection.user_id)
                    except Exception as exc:
                        logger.warning("connection_manager.ping_failed_disconnecting", connection_id=connection_id, error=str(exc))
                        await self.disconnect(connection_id)
            except asyncio.CancelledError:
                raise


_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


__all__ = ["ConnectionManager", "ConnectionLimitReached", "get_connection_manager", "MAX_CONNECTIONS", "HEARTBEAT_INTERVAL_SECONDS", "HEARTBEAT_TIMEOUT_SECONDS"]
