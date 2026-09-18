"""Modèle Client : la structure racine du multi-tenant. Presque toutes les autres
tables portent un client_id qui isole les données par client."""

from typing import Optional

from sqlalchemy import ARRAY, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.base import Base


class Client(Base):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(255))
    website: Mapped[Optional[str]] = mapped_column(String(500))

    # Charte éditoriale (ton, style, contraintes) consultée par l'Agent Content
    editorial_guidelines: Mapped[Optional[dict]] = mapped_column(JSONB)
    # Palette de marque, ex. {"primary": "#0A0A0A", "secondary": "#FFFFFF"}
    brand_colors: Mapped[Optional[dict]] = mapped_column(JSONB)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))

    forbidden_topics: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    # Cible démographique/comportementale utilisée pour orienter la génération de contenu
    target_audience: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Configuration des intégrations tierces (Google Search Console, Google
    # Ads, Meta, Mautic, Matomo, n8n)  ex. {"google_ads": {"api_key": "...",
    # "connected": true}}. Stocke la config/les identifiants fournis par le
    # client, PAS un flux OAuth2 réel (aucune infrastructure de callback
    # OAuth n'existe dans ce backend) : "connected" ci-dessus est déclaratif
    # (saisi par l'utilisateur), pas vérifié par un vrai handshake.
    integrations: Mapped[Optional[dict]] = mapped_column(JSONB)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Client id={self.id} name={self.name!r}>"
