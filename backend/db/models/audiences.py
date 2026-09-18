"""Modèles Contact (base de contacts marketing, synchronisée avec Mautic) et
EmailSequence (progression d'un contact dans une séquence email automatisée)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.base import Base
from backend.db.models.enums import EmailSequenceStatus


class Contact(Base):
    __tablename__ = "contacts"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255))
    last_name: Mapped[Optional[str]] = mapped_column(String(255))

    segment_tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    # Historique comportemental agrégé (pages vues, produits consultés, achats...)
    behavior_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    lead_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    last_interaction_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    opted_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Contact id={self.id} email={self.email!r}>"


class EmailSequence(Base):
    __tablename__ = "email_sequences"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nom logique de la séquence, ex. "welcome", "nurturing", "reactivation"
    sequence_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[EmailSequenceStatus] = mapped_column(
        Enum(EmailSequenceStatus, name="email_sequence_status"),
        nullable=False,
        default=EmailSequenceStatus.PENDING,
        index=True,
    )

    triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EmailSequence id={self.id} sequence={self.sequence_name!r} step={self.current_step}>"
