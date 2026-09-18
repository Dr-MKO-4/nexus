"""Cache des décisions de routage LiteLLM (quel provider/modèle pour une
tâche donnée), pour éviter de recalculer le routage à chaque appel LLM
identique. Les statistiques hit/miss exposées ici sont destinées à être
relayées vers LangFuse par l'appelant (le LLM gateway, Phase 3)  ce
module ne dépend pas directement du SDK LangFuse.
"""

from datetime import datetime, timezone

import structlog
from pydantic import BaseModel

from backend.core.memory.redis_client import RedisClient, get_redis_client

logger = structlog.get_logger(__name__)

DEFAULT_ROUTING_TTL_SECONDS = 300

_ROUTING_KEY_PREFIX = "routing:decision:"
_STATS_HITS_KEY = "routing:stats:hits"
_STATS_MISSES_KEY = "routing:stats:misses"


class RoutingDecision(BaseModel):
    provider: str
    model: str
    cached_at: datetime
    ttl: int = DEFAULT_ROUTING_TTL_SECONDS


class RoutingCache:
    def __init__(self, redis_client: RedisClient | None = None) -> None:
        self._redis = redis_client or get_redis_client()

    @staticmethod
    def _key(task_hash: str) -> str:
        return f"{_ROUTING_KEY_PREFIX}{task_hash}"

    async def cache_routing_decision(
        self, task_hash: str, provider: str, model: str, ttl: int = DEFAULT_ROUTING_TTL_SECONDS
    ) -> None:
        decision = RoutingDecision(
            provider=provider, model=model, cached_at=datetime.now(timezone.utc), ttl=ttl
        )
        await self._redis.set(self._key(task_hash), decision.model_dump(mode="json"), ttl=ttl)
        logger.debug(
            "routing_cache.stored", task_hash=task_hash, provider=provider, model=model, ttl=ttl
        )

    async def get_routing_decision(self, task_hash: str) -> RoutingDecision | None:
        raw = await self._redis.get(self._key(task_hash))
        if raw is None:
            await self._redis.incr(_STATS_MISSES_KEY)
            logger.debug("routing_cache.miss", task_hash=task_hash)
            return None

        await self._redis.incr(_STATS_HITS_KEY)
        logger.debug("routing_cache.hit", task_hash=task_hash)
        return RoutingDecision.model_validate(raw)

    async def invalidate_routing_cache(self) -> int:
        """Supprime toutes les décisions de routage en cache, pour forcer un
        recalcul complet (ex. après un changement de configuration des
        providers). Retourne le nombre d'entrées invalidées."""
        keys = await self._redis.scan_keys(f"{_ROUTING_KEY_PREFIX}*")
        for key in keys:
            await self._redis.delete(key)
        logger.info("routing_cache.invalidated", count=len(keys))
        return len(keys)

    async def get_cache_stats(self) -> dict:
        """Statistiques hit/miss cumulées, à pousser vers LangFuse par l'appelant."""
        hits = int(await self._redis.get(_STATS_HITS_KEY) or 0)
        misses = int(await self._redis.get(_STATS_MISSES_KEY) or 0)
        total = hits + misses
        stats = {
            "hits": hits,
            "misses": misses,
            "total": total,
            "hit_rate": hits / total if total else 0.0,
        }
        logger.debug("routing_cache.stats", **stats)
        return stats
