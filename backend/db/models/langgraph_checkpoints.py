"""Schéma reflétant ce qu'attend PostgresSaver de LangGraph pour persister
l'état des threads d'exécution (checkpoints du graphe d'orchestration).

Note : en pratique, `PostgresSaver.setup()` crée et gère ses propres tables
au démarrage de l'application  ce modèle documente ce schéma dans notre
registre SQLAlchemy/Alembic pour qu'il apparaisse dans les migrations et
reste lisible/interrogeable depuis le reste du code (ex. debug, time-travel
en dehors de l'API LangGraph). Il hérite de `DeclarativeRoot` et non de
`Base` : la clé primaire composite (thread_id, checkpoint_id) est imposée
par ce schéma, incompatible avec l'UUID unique du mixin standard.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models.base import DeclarativeRoot


class LangGraphCheckpoint(DeclarativeRoot):
    __tablename__ = "langgraph_checkpoints"

    thread_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(255))

    checkpoint_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Attribut Python "metadata_" pour ne pas entrer en conflit avec
    # DeclarativeBase.metadata ; le nom de colonne réel reste "metadata".
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LangGraphCheckpoint thread_id={self.thread_id!r} checkpoint_id={self.checkpoint_id!r}>"
