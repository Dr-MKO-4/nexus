"""Repositories pour PerformanceMetric et AgentDecision."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from backend.db.models.performance import AgentDecision, PerformanceMetric
from backend.db.repositories.base_repository import BaseRepository


class PerformanceMetricRepository(BaseRepository[PerformanceMetric]):
    model = PerformanceMetric

    async def get_by_campaign(self, campaign_id: UUID) -> Sequence[PerformanceMetric]:
        result = await self.session.execute(
            select(PerformanceMetric).where(PerformanceMetric.campaign_id == campaign_id)
        )
        return result.scalars().all()

    async def get_by_client_and_period(
        self, client_id: UUID, period_start: datetime, period_end: datetime
    ) -> Sequence[PerformanceMetric]:
        """Ajouté au Prompt 7.1 (GET /analytics/channels : "performances par
        canal", donc TOUS les canaux d'un client sur la période  contrairement
        à `get_by_channel_and_period` ci-dessous, qui exige un canal unique)."""
        result = await self.session.execute(
            select(PerformanceMetric).where(
                PerformanceMetric.client_id == client_id,
                PerformanceMetric.period_start >= period_start,
                PerformanceMetric.period_end <= period_end,
            )
        )
        return result.scalars().all()

    async def get_by_channel_and_period(
        self, client_id: UUID, channel: str, period_start: datetime, period_end: datetime
    ) -> Sequence[PerformanceMetric]:
        result = await self.session.execute(
            select(PerformanceMetric).where(
                PerformanceMetric.client_id == client_id,
                PerformanceMetric.channel == channel,
                PerformanceMetric.period_start >= period_start,
                PerformanceMetric.period_end <= period_end,
            )
        )
        return result.scalars().all()


class AgentDecisionRepository(BaseRepository[AgentDecision]):
    model = AgentDecision

    async def get_by_agent(self, client_id: UUID, agent_name: str) -> Sequence[AgentDecision]:
        result = await self.session.execute(
            select(AgentDecision)
            .where(AgentDecision.client_id == client_id, AgentDecision.agent_name == agent_name)
            .order_by(AgentDecision.created_at.desc())
        )
        return result.scalars().all()

    async def get_by_type(
        self, client_id: UUID, decision_type: str, *, since: datetime | None = None, limit: int = 100
    ) -> Sequence[AgentDecision]:
        """Ajouté au Prompt 7.1 (GET /analytics/anomalies : décisions du type
        "anomaly_detected" pour un client)."""
        stmt = select(AgentDecision).where(AgentDecision.client_id == client_id, AgentDecision.decision_type == decision_type)
        if since is not None:
            stmt = stmt.where(AgentDecision.created_at >= since)
        stmt = stmt.order_by(AgentDecision.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_recent_by_agent(
        self, agent_name: str, *, client_id: UUID | None = None, limit: int = 50
    ) -> Sequence[AgentDecision]:
        """Décisions récentes d'un agent, TOUS clients confondus si
        `client_id` est omis  ajouté au Prompt 7.1 pour GET /agents/{name}/logs
        (statut/logs "globaux", pas nécessairement scopés à un client, à la
        différence de `get_by_agent` ci-dessus qui exige un client_id)."""
        stmt = select(AgentDecision).where(AgentDecision.agent_name == agent_name)
        if client_id is not None:
            stmt = stmt.where(AgentDecision.client_id == client_id)
        stmt = stmt.order_by(AgentDecision.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_client(
        self, client_id: UUID, *, since: datetime | None = None, limit: int = 200
    ) -> Sequence[AgentDecision]:
        """Décisions de TOUS les agents pour ce client (contrairement à
        `get_by_agent`, restreint à un seul)  nécessaire pour
        `agents.reporting.nodes.load_report_context_node` ("les décisions de
        la semaine", tous agents confondus). `since` filtre optionnellement
        sur `created_at >=` (ex. début de la période du rapport)."""
        stmt = select(AgentDecision).where(AgentDecision.client_id == client_id)
        if since is not None:
            stmt = stmt.where(AgentDecision.created_at >= since)
        stmt = stmt.order_by(AgentDecision.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
