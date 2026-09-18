"""Repositories pour Campaign et CampaignCheckpoint."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from backend.db.models.campaigns import Campaign, CampaignCheckpoint
from backend.db.models.enums import CampaignStatus
from backend.db.repositories.base_repository import BaseRepository


class CampaignRepository(BaseRepository[Campaign]):
    model = Campaign

    async def get_by_client(
        self, client_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Campaign]:
        result = await self.session.execute(
            select(Campaign)
            .where(Campaign.client_id == client_id)
            .order_by(Campaign.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_active_campaigns(self, client_id: UUID | None = None) -> Sequence[Campaign]:
        stmt = select(Campaign).where(Campaign.status == CampaignStatus.ACTIVE)
        if client_id is not None:
            stmt = stmt.where(Campaign.client_id == client_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_status(self, status: CampaignStatus, client_id: UUID | None = None) -> Sequence[Campaign]:
        """Ajouté au Prompt 7.1 (GET /hitl/pending : campagnes PAUSED en
        attente de validation humaine)  généralise `get_active_campaigns`
        (ACTIVE en dur) à un statut arbitraire."""
        stmt = select(Campaign).where(Campaign.status == status)
        if client_id is not None:
            stmt = stmt.where(Campaign.client_id == client_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class CampaignCheckpointRepository(BaseRepository[CampaignCheckpoint]):
    model = CampaignCheckpoint

    async def get_by_campaign(self, campaign_id: UUID) -> Sequence[CampaignCheckpoint]:
        result = await self.session.execute(
            select(CampaignCheckpoint)
            .where(CampaignCheckpoint.campaign_id == campaign_id)
            .order_by(CampaignCheckpoint.created_at.asc())
        )
        return result.scalars().all()

    async def get_latest_by_agent(
        self, campaign_id: UUID, agent_name: str
    ) -> CampaignCheckpoint | None:
        result = await self.session.execute(
            select(CampaignCheckpoint)
            .where(
                CampaignCheckpoint.campaign_id == campaign_id,
                CampaignCheckpoint.agent_name == agent_name,
            )
            .order_by(CampaignCheckpoint.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
