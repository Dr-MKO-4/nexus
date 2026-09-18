"""Repository pour LangGraphCheckpoint.

N'hérite pas de BaseRepository[T] : sa clé primaire est composite
(thread_id, checkpoint_id), incompatible avec `get_by_id(id_: UUID)`.
En pratique, l'écriture de ces lignes est gérée par PostgresSaver de
LangGraph lui-même ; ce repository sert surtout à la lecture (debug,
time-travel, interface d'administration).
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models.langgraph_checkpoints import LangGraphCheckpoint


class LangGraphCheckpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, thread_id: str, checkpoint_id: str) -> LangGraphCheckpoint | None:
        return await self.session.get(LangGraphCheckpoint, (thread_id, checkpoint_id))

    async def list_by_thread(self, thread_id: str) -> Sequence[LangGraphCheckpoint]:
        result = await self.session.execute(
            select(LangGraphCheckpoint)
            .where(LangGraphCheckpoint.thread_id == thread_id)
            .order_by(LangGraphCheckpoint.created_at.asc())
        )
        return result.scalars().all()

    async def get_latest_for_thread(self, thread_id: str) -> LangGraphCheckpoint | None:
        result = await self.session.execute(
            select(LangGraphCheckpoint)
            .where(LangGraphCheckpoint.thread_id == thread_id)
            .order_by(LangGraphCheckpoint.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
