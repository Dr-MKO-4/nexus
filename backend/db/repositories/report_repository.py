"""Repository pour Report."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from backend.db.models.reports import Report
from backend.db.repositories.base_repository import BaseRepository


class ReportRepository(BaseRepository[Report]):
    model = Report

    async def get_by_client(
        self, client_id: UUID, *, report_type: str | None = None, limit: int = 100, offset: int = 0
    ) -> Sequence[Report]:
        stmt = select(Report).where(Report.client_id == client_id)
        if report_type is not None:
            stmt = stmt.where(Report.report_type == report_type)
        stmt = stmt.order_by(Report.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()
