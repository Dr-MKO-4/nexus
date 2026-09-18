"""Client Redis async partagé : pool de connexions, sérialisation JSON
automatique, retry exponentiel, health check et décorateur de caching.

Toutes les autres briques de la couche mémoire (session_manager,
routing_cache) et l'interface de queues (tasks/queues/redis_queue.py)
s'appuient sur ce client plutôt que d'ouvrir leurs propres connexions.
"""

import asyncio
import functools
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, TypeVar

import structlog
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

T = TypeVar("T")

_MAX_RETRIES = 3
_BASE_RETRY_DELAY_SECONDS = 0.2


class RedisClient:
    """Wrapper async au-dessus de redis.asyncio, avec sérialisation JSON et retry."""

    def __init__(self, url: str | None = None) -> None:
        self._pool: ConnectionPool = ConnectionPool.from_url(
            url or str(settings.REDIS_URL),
            decode_responses=True,
            # RESP2 explicite : redis-py tente HELLO (RESP3) par défaut au
            # handshake, absente avant Redis 6.0 (donc incompatible avec des
            # serveurs plus anciens). RESP2 suffit intégralement à l'usage
            # get/set JSON de ce client  aucune perte fonctionnelle sur
            # redis:7-alpine (la cible réelle définie dans docker-compose.yml).
            protocol=2,
        )
        self._redis: Redis = Redis(connection_pool=self._pool)

    async def _with_retry(self, operation: str, call: Callable[[], Awaitable[T]]) -> T:
        """Exécute `call` avec un retry exponentiel (3 tentatives max) sur erreur Redis."""
        last_error: RedisError | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await call()
            except RedisError as exc:
                last_error = exc
                delay = _BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "redis.operation_retry",
                    operation=operation,
                    attempt=attempt,
                    max_retries=_MAX_RETRIES,
                    delay_seconds=delay,
                    error=str(exc),
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(delay)
        logger.error("redis.operation_failed", operation=operation, error=str(last_error))
        assert last_error is not None
        raise last_error

    async def get(self, key: str) -> Any | None:
        raw = await self._with_retry("get", lambda: self._redis.get(key))
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int | timedelta | None = None) -> None:
        payload = json.dumps(value, default=str)
        await self._with_retry("set", lambda: self._redis.set(key, payload, ex=ttl))
        logger.debug("redis.set", key=key, ttl=ttl)

    async def delete(self, key: str) -> int:
        deleted = await self._with_retry("delete", lambda: self._redis.delete(key))
        logger.debug("redis.delete", key=key, deleted=bool(deleted))
        return deleted

    async def expire(self, key: str, ttl: int | timedelta) -> bool:
        result = await self._with_retry("expire", lambda: self._redis.expire(key, ttl))
        logger.debug("redis.expire", key=key, ttl=ttl, applied=result)
        return result

    async def get_or_set(
        self, key: str, factory: Callable[[], Awaitable[Any]], ttl: int | timedelta = 300
    ) -> Any:
        """Retourne la valeur en cache, ou l'obtient via `factory()` et la met en cache.

        Limite connue : une valeur `None` mise en cache (JSON "null") est
        indiscernable d'une absence de clé au prochain appel (`get` renvoie
        `None` dans les deux cas)  `factory()` sera donc rappelée à chaque
        fois. Sans impact sur les usages actuels (session_manager,
        routing_cache) qui ne mettent jamais `None` en cache au niveau racine.
        """
        cached = await self.get(key)
        if cached is not None:
            logger.debug("redis.cache_hit", key=key)
            return cached
        logger.debug("redis.cache_miss", key=key)
        value = await factory()
        await self.set(key, value, ttl=ttl)
        return value

    async def scan_keys(self, pattern: str) -> list[str]:
        """Liste les clés correspondant à `pattern` (ex. "session:*"). Utilisé par
        session_manager/routing_cache pour lister/invalider par préfixe sans
        maintenir un index séparé qui pourrait se désynchroniser des TTL."""

        async def _scan() -> list[str]:
            keys: list[str] = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)
            return keys

        return await self._with_retry("scan_keys", _scan)

    async def incr(self, key: str) -> int:
        return await self._with_retry("incr", lambda: self._redis.incr(key))

    async def incrbyfloat(self, key: str, amount: float) -> float:
        """INCRBYFLOAT : incrément atomique pour des compteurs non-entiers
        (ex. coût cumulé en USD, cost_tracker.py). Redis stocke le résultat
        comme une chaîne décimale simple, compatible json.loads (utilisé par
        `get`)."""
        return await self._with_retry("incrbyfloat", lambda: self._redis.incrbyfloat(key, amount))

    async def llen(self, key: str) -> int:
        return await self._with_retry("llen", lambda: self._redis.llen(key))

    async def publish(self, channel: str, message: str) -> int:
        """Publie sur un canal Redis Pub/Sub  ajouté au Prompt 7.2
        (connection_manager.py) : diffusion d'événements WebSocket cross-
        instance. Pas de retry ici (contrairement aux autres méthodes) :
        Pub/Sub est du fire-and-forget par nature (aucun abonné = message
        perdu, même sans erreur réseau), retenter n'y changerait rien."""
        return await self._redis.publish(channel, message)

    def pubsub(self):
        """Retourne un objet PubSub natif redis-py  ajouté au Prompt 7.2.
        Pas de wrapper retry/JSON ici : `PubSub.listen()` est un générateur
        async à état (souscriptions), le faire transiter par `_with_retry`
        (conçu pour des appels ponctuels idempotents) romprait cet état à
        chaque tentative. L'appelant (connection_manager.py) gère lui-même
        la reconnexion de son abonnement."""
        return self._redis.pubsub()

    async def health_check(self) -> bool:
        try:
            pong = await self._redis.ping()
            return bool(pong)
        except RedisError as exc:
            logger.error("redis.health_check_failed", error=str(exc))
            return False

    async def close(self) -> None:
        await self._redis.aclose()
        await self._pool.disconnect()


_client: RedisClient | None = None


def get_redis_client() -> RedisClient:
    """Retourne le client Redis singleton, créé au premier appel."""
    global _client
    if _client is None:
        _client = RedisClient()
    return _client


def _build_cache_key(func: Callable, args: tuple, kwargs: dict) -> str:
    raw_key = f"{func.__module__}.{func.__qualname__}:{args!r}:{sorted(kwargs.items())!r}"
    digest = hashlib.sha256(raw_key.encode()).hexdigest()
    return f"fncache:{func.__qualname__}:{digest}"


def cache(ttl: int = 300) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Décorateur de caching Redis pour fonctions async.

    Met en cache la valeur de retour, avec une clé dérivée du nom qualifié
    de la fonction et de ses arguments. Ne s'applique qu'à des coroutines
    (cohérent avec la contrainte "tout async" de cette couche) : décorer
    une fonction synchrone lève une TypeError explicite plutôt que d'échouer
    silencieusement.
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"@cache ne peut décorer que des fonctions async ({func.__qualname__} ne l'est pas)")

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            client = get_redis_client()
            key = _build_cache_key(func, args, kwargs)
            return await client.get_or_set(key, lambda: func(*args, **kwargs), ttl=ttl)

        return wrapper

    return decorator
