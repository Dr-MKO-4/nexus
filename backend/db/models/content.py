"""Modèles Content (production éditoriale des agents) et ContentTemplate
(structures réutilisables, éventuellement liées à un fichier Figma/Canva)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.base import Base
from backend.db.models.enums import ContentPlatform, ContentStatus, ContentType


class Content(Base):
    __tablename__ = "contents"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    # Nom de l'agent producteur (ex. "content", "seo")  traçabilité de la génération
    agent_source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType, name="content_type"), nullable=False, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)

    platform: Mapped[ContentPlatform] = mapped_column(
        Enum(ContentPlatform, name="content_platform"), nullable=False, index=True
    )
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status"),
        nullable=False,
        default=ContentStatus.DRAFT,
        index=True,
    )

    # Métriques post-publication (impressions, clics, engagement...)
    performance_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    # Date de publication PRÉVUE (distincte de published_at, la date RÉELLE
    # une fois publié)  ajouté au Prompt 7.1 pour POST /contents/{id}/schedule
    # et GET /contents/calendar : aucune colonne de ce type n'existait avant
    # ce prompt, `published_at` seul ne peut pas représenter une publication
    # future non encore survenue.
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Content id={self.id} type={self.content_type} status={self.status}>"


class ContentTemplate(Base):
    __tablename__ = "content_templates"

    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Structure du template : sections, placeholders, contraintes de longueur...
    structure: Mapped[dict] = mapped_column(JSONB, nullable=False)

    figma_file_id: Mapped[Optional[str]] = mapped_column(String(255))
    canva_template_id: Mapped[Optional[str]] = mapped_column(String(255))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ContentTemplate id={self.id} type={self.template_type!r}>"
