"""Environnement Alembic, compatible SQLAlchemy async (moteur asyncpg).

Réutilise `backend.db.session.get_async_database_url()` pour rester
synchronisé avec `settings.DATABASE_URL` : aucune URL de connexion n'est
dupliquée dans alembic.ini.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Importe tous les modèles pour que Base.metadata (= DeclarativeRoot.metadata)
# connaisse l'intégralité des tables avant tout autogenerate.
from backend.db.models import Base  # noqa: F401
from backend.db.models.base import DeclarativeRoot
from backend.db.session import get_async_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = DeclarativeRoot.metadata


def run_migrations_offline() -> None:
    """Génère le SQL des migrations sans connexion active à la base (`alembic upgrade --sql`)."""
    context.configure(
        url=get_async_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Applique les migrations via une connexion asyncpg réelle."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_async_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
