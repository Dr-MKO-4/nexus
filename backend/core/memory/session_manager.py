"""Gestionnaire de sessions des agents : état de travail court terme d'un
agent sur une campagne, persisté dans Redis avec expiration automatique
(TTL) plutôt que suppression explicite en fin de session.
"""

import uuid
from datetime import datetime, timezone

import structlog
from pydantic import BaseModel, Field

from backend.core.memory.redis_client import RedisClient, get_redis_client

logger = structlog.get_logger(__name__)

DEFAULT_SESSION_TTL_SECONDS = 24 * 60 * 60  # 24h

_SESSION_KEY_PREFIX = "session:"


class SessionData(BaseModel):
    session_id: str
    agent_name: str
    campaign_id: str | None = None
    client_id: str | None = None

    # Contexte courant de l'agent (mémoire de travail)
    context: dict = Field(default_factory=dict)
    # Résultats partiels accumulés pendant un fanout parallèle (Send API LangGraph)
    intermediate_results: dict = Field(default_factory=dict)

    started_at: datetime
    last_active_at: datetime
    ttl: int = DEFAULT_SESSION_TTL_SECONDS


class SessionManager:
    def __init__(self, redis_client: RedisClient | None = None) -> None:
        self._redis = redis_client or get_redis_client()

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{_SESSION_KEY_PREFIX}{session_id}"

    async def create_session(
        self,
        agent_name: str,
        campaign_id: str | None = None,
        client_id: str | None = None,
        ttl: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        session = SessionData(
            session_id=session_id,
            agent_name=agent_name,
            campaign_id=campaign_id,
            client_id=client_id,
            started_at=now,
            last_active_at=now,
            ttl=ttl,
        )
        await self._redis.set(self._key(session_id), session.model_dump(mode="json"), ttl=ttl)
        logger.info(
            "session.created",
            session_id=session_id,
            agent_name=agent_name,
            campaign_id=campaign_id,
            ttl=ttl,
        )
        return session_id

    async def get_session(self, session_id: str) -> SessionData | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            logger.debug("session.not_found", session_id=session_id)
            return None
        return SessionData.model_validate(raw)

    async def update_session(self, session_id: str, data: dict) -> None:
        """Met à jour partiellement une session existante (merge des champs fournis)
        et rafraîchit son TTL. Ne recrée pas la session si elle est absente/expirée."""
        session = await self.get_session(session_id)
        if session is None:
            logger.warning("session.update_missing", session_id=session_id)
            return

        updated = session.model_copy(update={**data, "last_active_at": datetime.now(timezone.utc)})
        await self._redis.set(self._key(session_id), updated.model_dump(mode="json"), ttl=updated.ttl)
        logger.info("session.updated", session_id=session_id, fields=list(data.keys()))

    async def delete_session(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))
        logger.info("session.deleted", session_id=session_id)

    async def list_active_sessions(self) -> list[SessionData]:
        """Liste toutes les sessions non expirées. S'appuie sur un scan par préfixe
        plutôt qu'un index séparé : une session expirée disparaît naturellement
        du résultat dès l'expiration de sa clé Redis, sans synchronisation à gérer."""
        keys = await self._redis.scan_keys(f"{_SESSION_KEY_PREFIX}*")
        sessions: list[SessionData] = []
        for key in keys:
            raw = await self._redis.get(key)
            if raw is not None:
                sessions.append(SessionData.model_validate(raw))
        return sessions
