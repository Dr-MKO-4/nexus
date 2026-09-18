"""Classes de base SQLAlchemy 2.0 (style déclaratif async) partagées par tous les modèles.

Deux classes :
- `DeclarativeRoot` : le registre déclaratif racine, nu (aucune colonne). C'est
  `DeclarativeRoot.metadata` qui sert de cible à Alembic (voir
  backend/db/migrations/env.py) pour découvrir toutes les tables.
- `Base` : le mixin qu'utilise la quasi-totalité des modèles  clé primaire
  UUID générée côté application, timestamps `created_at`/`updated_at`
  automatiques, et `to_dict()` pour la sérialisation.

Le modèle LangGraphCheckpoint (langgraph_checkpoints.py) est le seul à hériter
directement de `DeclarativeRoot` : sa clé primaire composite (thread_id,
checkpoint_id) est imposée par le schéma attendu par PostgresSaver de
LangGraph, incompatible avec la clé UUID unique de `Base`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DeclarativeRoot(DeclarativeBase):
    """Registre déclaratif racine, sans colonnes. Cible unique pour Alembic."""


class Base(DeclarativeRoot):
    """Mixin standard : UUID comme clé primaire, timestamps automatiques, to_dict()."""

    # __abstract__ empêche SQLAlchemy de mapper cette classe elle-même comme une
    # table ; les colonnes ci-dessous sont héritées par chaque sous-classe
    # concrète (qui définit son propre __tablename__).
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict[str, Any]:
        """Sérialise les colonnes mappées en dict (UUID/datetime laissés tels quels)."""
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}
