"""add_client_integrations

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18 00:00:00

Ajoute `clients.integrations` (JSONB)  section "Intégrations" de
Settings.tsx (audit frontend/backend) : stocke la config/les identifiants
que le client fournit pour chaque service tiers (Google Ads, Meta, etc.),
PAS un flux OAuth2 réel (aucune infrastructure de callback OAuth n'existe
dans ce backend). Écrite à la main, comme 0001, en l'absence de base vivante
dans cet environnement  à revalider avec `alembic check` une fois une base
disponible.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("integrations", postgresql.JSONB))


def downgrade() -> None:
    op.drop_column("clients", "integrations")
