"""Tracker de coût LLM en temps réel, stocké dans Redis avec des clés à TTL
24h (une nouvelle journée = compteurs repartis de zéro, sans job de purge à
maintenir).
"""

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import structlog

from backend.config.settings import settings
from backend.core.memory.redis_client import RedisClient, get_redis_client

logger = structlog.get_logger(__name__)

DAILY_TTL_SECONDS = 24 * 60 * 60

# Callback optionnel appelé quand le budget journalier est dépassé, avec le
# coût cumulé du jour. La diffusion WebSocket réelle (mentionnée dans le
# Prompt 3.1) n'existe pas encore : backend/api/websocket/ n'est encore qu'un
# stub (__init__.py vide). En attendant, ce callback permet de brancher
# l'alerte sans coupler ce module à une implémentation WebSocket qui n'existe
# pas  à câbler sur connection_manager.py une fois écrit.
BudgetAlertCallback = Callable[[float], Awaitable[None]]


class CostTracker:
    def __init__(
        self,
        redis_client: RedisClient | None = None,
        on_budget_exceeded: BudgetAlertCallback | None = None,
    ) -> None:
        self._redis = redis_client or get_redis_client()
        self._on_budget_exceeded = on_budget_exceeded

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _key(self, *parts: str) -> str:
        return ":".join(("llm_cost", self._today(), *parts))

    async def track_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        agent_name: str | None = None,
    ) -> None:
        keys = [self._key("total"), self._key("provider", provider), self._key("model", model)]
        if agent_name:
            keys.append(self._key("agent", agent_name))

        for key in keys:
            await self._redis.incrbyfloat(key, cost)
            # INCRBYFLOAT ne prend pas de TTL : on le (ré)applique à chaque
            # écriture pour que la clé continue d'expirer 24h après la
            # DERNIÈRE utilisation du jour, pas la première.
            await self._redis.expire(key, DAILY_TTL_SECONDS)

        logger.info(
            "cost_tracker.usage_tracked",
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            agent_name=agent_name,
        )

        if await self.check_budget_exceeded():
            await self._alert_budget_exceeded()

    async def get_daily_cost(self) -> float:
        raw = await self._redis.get(self._key("total"))
        return float(raw) if raw is not None else 0.0

    async def _aggregate_by(self, dimension: str) -> dict[str, float]:
        prefix = self._key(dimension, "")
        keys = await self._redis.scan_keys(f"{prefix}*")
        result: dict[str, float] = {}
        for key in keys:
            name = key.rsplit(":", 1)[-1]
            raw = await self._redis.get(key)
            result[name] = float(raw) if raw is not None else 0.0
        return result

    async def get_cost_by_agent(self) -> dict[str, float]:
        return await self._aggregate_by("agent")

    async def get_cost_by_model(self) -> dict[str, float]:
        return await self._aggregate_by("model")

    async def check_budget_exceeded(self) -> bool:
        daily_cost = await self.get_daily_cost()
        return daily_cost >= settings.HYBRID_COST_DAILY_LIMIT_USD

    async def _alert_budget_exceeded(self) -> None:
        daily_cost = await self.get_daily_cost()
        logger.warning(
            "cost_tracker.budget_exceeded",
            daily_cost=daily_cost,
            limit=settings.HYBRID_COST_DAILY_LIMIT_USD,
        )
        if self._on_budget_exceeded is not None:
            await self._on_budget_exceeded(daily_cost)
