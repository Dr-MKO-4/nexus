"""Modèles Campaign (unité de travail de l'Orchestrateur) et CampaignCheckpoint
(snapshots intermédiaires déposés par les agents pendant l'exécution)."""

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.base import Base
from backend.db.models.enums import CampaignStatus


class Campaign(Base):
    __tablename__ = "campaigns"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Objectif business en langage naturel, tel que fourni à l'Orchestrateur
    objective: Mapped[str] = mapped_column(String, nullable=False)

    budget_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    budget_consumed: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status"),
        nullable=False,
        default=CampaignStatus.DRAFT,
        index=True,
    )

    # Répartition budgétaire par canal, ex. {"seo": 0.2, "sea": 0.5, "social": 0.3}
    channel_allocations: Mapped[Optional[dict]] = mapped_column(JSONB)

    start_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, index=True)

    # Résultats consolidés en fin de campagne (KPIs finaux, synthèse)
    results: Mapped[Optional[dict]] = mapped_column(JSONB)

    # thread_id LangGraph (= MarketingState.session_id, voir main_graph.py) 
    # ajouté au Prompt 7.1 : sans cette colonne, backend/api/routes/campaigns.py
    # n'aurait aucun moyen de retrouver le thread à reprendre/inspecter
    # (pause/resume/history) après la création de la campagne, le seul champ
    # reliant une ligne Campaign à son exécution LangGraph.
    thread_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Campaign id={self.id} name={self.name!r} status={self.status}>"


class CampaignCheckpoint(Base):
    """Snapshot de l'état d'un agent à un instant donné pendant une campagne.

    Distinct des checkpoints LangGraph (langgraph_checkpoints.py) : ceux-ci sont
    des points de repère métier lisibles par un humain, pas l'état brut du graphe.
    """

    __tablename__ = "campaign_checkpoints"

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    checkpoint_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CampaignCheckpoint id={self.id} agent={self.agent_name!r}>"
