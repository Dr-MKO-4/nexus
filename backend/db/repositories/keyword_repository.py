"""Repositories pour Keyword et KeywordHistory."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from backend.db.models.keywords import Keyword, KeywordHistory
from backend.db.repositories.base_repository import BaseRepository


class KeywordRepository(BaseRepository[Keyword]):
    model = Keyword

    async def get_by_client(self, client_id: UUID) -> Sequence[Keyword]:
        result = await self.session.execute(select(Keyword).where(Keyword.client_id == client_id))
        return result.scalars().all()

    async def get_by_term(self, client_id: UUID, term: str) -> Keyword | None:
        result = await self.session.execute(
            select(Keyword).where(Keyword.client_id == client_id, Keyword.term == term)
        )
        return result.scalar_one_or_none()


class KeywordHistoryRepository(BaseRepository[KeywordHistory]):
    model = KeywordHistory

    async def get_history_for_keyword(self, keyword_id: UUID) -> Sequence[KeywordHistory]:
        result = await self.session.execute(
            select(KeywordHistory)
            .where(KeywordHistory.keyword_id == keyword_id)
            .order_by(KeywordHistory.date.asc())
        )
        return result.scalars().all()
