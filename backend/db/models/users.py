"""Modèle User : comptes accédant à l'interface NEXUS AI, rattachés à un client
(ou à aucun pour les rôles internes admin)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.base import Base
from backend.db.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.VIEWER, index=True
    )
    # NULL pour les comptes internes (admin) non rattachés à un client unique
    client_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
