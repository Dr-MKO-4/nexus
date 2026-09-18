"""Modèle Report : rapports générés par l'Agent Reporting (hebdomadaires,
par campagne, ou de crise)  Prompt 5.8."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.base import Base


class Report(Base):
    __tablename__ = "reports"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "weekly" | "campaign" | "crisis"  pas d'Enum SQL dédié : ce champ peut
    # grandir librement (nouveaux types de rapport) sans migration de schéma.
    report_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    period: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    # Contenu structuré complet (WeeklyReport/CampaignReport/CrisisReport.model_dump())
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(500))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Report id={self.id} type={self.report_type!r} period={self.period!r}>"
