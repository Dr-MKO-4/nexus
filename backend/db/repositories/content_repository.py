"""Repositories pour Content et ContentTemplate."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select

from backend.db.models.content import Content, ContentTemplate
from backend.db.models.enums import ContentStatus
from backend.db.repositories.base_repository import BaseRepository


class ContentRepository(BaseRepository[Content]):
    model = Content

    async def get_by_client(
        self, client_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Content]:
        result = await self.session.execute(
            select(Content)
            .where(Content.client_id == client_id)
            .order_by(Content.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_campaign(self, campaign_id: UUID) -> Sequence[Content]:
        result = await self.session.execute(
            select(Content).where(Content.campaign_id == campaign_id)
        )
        return result.scalars().all()

    async def get_published(self, client_id: UUID) -> Sequence[Content]:
        result = await self.session.execute(
            select(Content).where(
                Content.client_id == client_id,
                Content.status == ContentStatus.PUBLISHED,
            )
        )
        return result.scalars().all()

    async def get_calendar(self, client_id: UUID, start: datetime, end: datetime) -> Sequence[Content]:
        """Calendrier éditorial (GET /contents/calendar, Prompt 7.1) : tout
        contenu dont la date PRÉVUE (`scheduled_at`) OU RÉELLE
        (`published_at`) tombe dans la période  `or_` nécessaire puisqu'un
        contenu déjà publié n'a typiquement plus de `scheduled_at` renseigné
        (voir routes/content.py: publish_content écrase published_at sans
        toucher scheduled_at, les deux champs restent donc indépendants)."""
        result = await self.session.execute(
            select(Content)
            .where(
                Content.client_id == client_id,
                or_(
                    Content.scheduled_at.between(start, end),
                    Content.published_at.between(start, end),
                ),
            )
            .order_by(func.coalesce(Content.scheduled_at, Content.published_at))
        )
        return result.scalars().all()


class ContentTemplateRepository(BaseRepository[ContentTemplate]):
    model = ContentTemplate

    async def get_by_client_and_type(
        self, client_id: UUID, template_type: str
    ) -> Sequence[ContentTemplate]:
        result = await self.session.execute(
            select(ContentTemplate).where(
                ContentTemplate.client_id == client_id,
                ContentTemplate.template_type == template_type,
            )
        )
        return result.scalars().all()
