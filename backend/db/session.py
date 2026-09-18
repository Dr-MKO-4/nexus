"""Moteur SQLAlchemy async et factory de sessions, partagés par l'API,
les workers Celery et Alembic (voir backend/db/migrations/env.py).

`settings.DATABASE_URL` est un `PostgresDsn` Pydantic au schéma
`postgresql://...` (validation standard) ; le driver async utilisé ici est
asyncpg, d'où la réécriture du schéma en `postgresql+asyncpg://...`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from backend.config.settings import settings


def get_async_database_url() -> str:
    """Convertit DATABASE_URL (schéma postgresql://) vers le schéma asyncpg."""
    return str(settings.DATABASE_URL).replace("postgresql://", "postgresql+asyncpg://", 1)


engine: AsyncEngine = create_async_engine(
    get_async_database_url(),
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Fournit une session avec commit automatique en sortie de bloc, rollback sur erreur.

    Usage : `async with get_session() as session: ...`
    Pour FastAPI, préférer une dépendance dédiée qui appelle ce même
    context manager (voir backend/api/routes).
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
