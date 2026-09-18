"""Modèles Keyword (suivi SEO) et KeywordHistory (historique de position, une
ligne par relevé, utilisé pour tracer l'évolution dans le temps)."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.base import Base


class Keyword(Base):
    __tablename__ = "keywords"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    term: Mapped[str] = mapped_column(String(500), nullable=False, index=True)

    search_volume: Mapped[Optional[int]] = mapped_column(Integer)
    difficulty: Mapped[Optional[float]] = mapped_column(Float)
    current_position: Mapped[Optional[int]] = mapped_column(Integer)
    target_position: Mapped[Optional[int]] = mapped_column(Integer)

    # Cluster sémantique : {"cluster_name": "...", "related_terms": [...]}
    cluster: Mapped[Optional[dict]] = mapped_column(JSONB)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Keyword id={self.id} term={self.term!r}>"


class KeywordHistory(Base):
    __tablename__ = "keyword_history"

    keyword_id: Mapped[UUID] = mapped_column(
        ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KeywordHistory keyword_id={self.keyword_id} date={self.date} position={self.position}>"
