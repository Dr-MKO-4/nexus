"""Modèles PerformanceMetric (KPIs cross-canal) et AgentDecision (journal des
décisions prises par les agents, avec leur résultat  base pour l'apprentissage
et l'audit)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.base import Base


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    channel: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PerformanceMetric {self.metric_name}={self.metric_value} channel={self.channel!r}>"


class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    decision_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Contexte et raisonnement ayant mené à la décision
    decision_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Résultat observé a posteriori (impact mesuré, succès/échec)  rempli après coup
    outcome: Mapped[Optional[dict]] = mapped_column(JSONB)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AgentDecision id={self.id} agent={self.agent_name!r} type={self.decision_type!r}>"
