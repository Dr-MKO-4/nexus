"""Client Qdrant async : connexion, initialisation des collections au
démarrage, opérations CRUD vectorielles de base avec retry.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Filter, PointIdsList, PointStruct

from backend.config.settings import settings
from backend.core.memory.collections import initialize_collections

logger = structlog.get_logger(__name__)

T = TypeVar("T")

_MAX_RETRIES = 3
_BASE_RETRY_DELAY_SECONDS = 0.2

# Erreurs considérées transitoires (panne réseau ou service Qdrant temporairement
# indisponible) et donc éligibles au retry, par opposition à une erreur de
# programmation (mauvais type d'argument, etc.) qu'il ne faut pas masquer.
_RETRYABLE_ERRORS = (UnexpectedResponse, ConnectionError, TimeoutError, OSError)


class QdrantMemoryClient:
    """Wrapper async au-dessus d'AsyncQdrantClient : upsert/search/get/delete + retry."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self._client = AsyncQdrantClient(
            host=host or settings.QDRANT_HOST,
            port=port or settings.QDRANT_PORT,
        )

    async def _with_retry(self, operation: str, call: Callable[[], Awaitable[T]]) -> T:
        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await call()
            except _RETRYABLE_ERRORS as exc:
                last_error = exc
                delay = _BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "qdrant.operation_retry",
                    operation=operation,
                    attempt=attempt,
                    max_retries=_MAX_RETRIES,
                    delay_seconds=delay,
                    error=str(exc),
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(delay)
        logger.error("qdrant.operation_failed", operation=operation, error=str(last_error))
        assert last_error is not None
        raise last_error

    async def ensure_collections(self) -> None:
        """Crée les collections manquantes. À appeler une fois au démarrage de l'application."""
        await self._with_retry("ensure_collections", lambda: initialize_collections(self._client))

    async def upsert(
        self, collection_name: str, point_id: str, vector: list[float], payload: dict[str, Any]
    ) -> None:
        async def _upsert() -> None:
            await self._client.upsert(
                collection_name=collection_name,
                points=[PointStruct(id=point_id, vector=vector, payload=payload)],
            )

        await self._with_retry("upsert", _upsert)
        logger.debug("qdrant.upserted", collection=collection_name, point_id=point_id)

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        query_filter: Filter | None = None,
    ) -> list[dict[str, Any]]:
        async def _search() -> list[dict[str, Any]]:
            response = await self._client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
            return [{"id": point.id, "score": point.score, "payload": point.payload or {}} for point in response.points]

        results = await self._with_retry("search", _search)
        logger.debug("qdrant.searched", collection=collection_name, limit=limit, hits=len(results))
        return results

    async def get_by_id(self, collection_name: str, point_id: str) -> dict[str, Any] | None:
        async def _retrieve() -> list:
            return await self._client.retrieve(
                collection_name=collection_name, ids=[point_id], with_payload=True
            )

        records = await self._with_retry("get_by_id", _retrieve)
        if not records:
            return None
        record = records[0]
        return {"id": record.id, "payload": record.payload or {}}

    async def delete(self, collection_name: str, point_id: str) -> None:
        async def _delete() -> None:
            await self._client.delete(
                collection_name=collection_name,
                points_selector=PointIdsList(points=[point_id]),
            )

        await self._with_retry("delete", _delete)
        logger.debug("qdrant.deleted", collection=collection_name, point_id=point_id)

    async def health_check(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception as exc:  # santé du service : on ne veut jamais lever ici
            logger.error("qdrant.health_check_failed", error=str(exc))
            return False

    async def close(self) -> None:
        await self._client.close()


_client: QdrantMemoryClient | None = None


def get_qdrant_client() -> QdrantMemoryClient:
    """Retourne le client Qdrant singleton, créé au premier appel."""
    global _client
    if _client is None:
        _client = QdrantMemoryClient()
    return _client
