"""create_all_tables

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00

Migration initiale : crée l'intégralité du schéma NEXUS AI (13 tables), dans
l'ordre imposé par les dépendances de clés étrangères. Écrite à la main
(reflétant exactement backend/db/models/) plutôt que générée par
`alembic revision --autogenerate`, en l'absence de base vivante dans cet
environnement  à revalider avec `alembic check` une fois une base
disponible.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamp_columns() -> list[sa.Column]:
    """Colonnes id/created_at/updated_at communes à toutes les tables issues de Base."""
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    # --- clients (racine du multi-tenant, référencée par la plupart des autres tables) ---
    op.create_table(
        "clients",
        *_timestamp_columns(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(255)),
        sa.Column("website", sa.String(500)),
        sa.Column("editorial_guidelines", postgresql.JSONB),
        sa.Column("brand_colors", postgresql.JSONB),
        sa.Column("logo_url", sa.String(500)),
        sa.Column("forbidden_topics", postgresql.ARRAY(sa.String)),
        sa.Column("target_audience", postgresql.JSONB),
    )
    op.create_index("ix_clients_name", "clients", ["name"])

    # --- campaigns ---
    # "archived" ajouté au Prompt 7.1 (DELETE /campaigns/{id}, archivage
    # plutôt que suppression physique  voir db/models/enums.py) : ajouté
    # directement à la liste de valeurs de ce type ENUM natif Postgres,
    # PAS via `ALTER TYPE ... ADD VALUE` (inutile ici : cette migration
    # n'a encore jamais été appliquée à une base réelle à ce stade du
    # projet, donc rien à altérer rétroactivement).
    campaign_status = postgresql.ENUM(
        "draft", "active", "paused", "completed", "archived", name="campaign_status"
    )
    campaign_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "campaigns",
        *_timestamp_columns(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("objective", sa.String, nullable=False),
        sa.Column("budget_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("budget_consumed", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", campaign_status, nullable=False, server_default="draft"),
        sa.Column("channel_allocations", postgresql.JSONB),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("results", postgresql.JSONB),
        # thread_id LangGraph  ajouté au Prompt 7.1 (voir db/models/campaigns.py).
        sa.Column("thread_id", sa.String(64), unique=True),
    )
    op.create_index("ix_campaigns_client_id", "campaigns", ["client_id"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])
    op.create_index("ix_campaigns_start_date", "campaigns", ["start_date"])
    op.create_index("ix_campaigns_end_date", "campaigns", ["end_date"])
    op.create_index("ix_campaigns_thread_id", "campaigns", ["thread_id"])

    # --- campaign_checkpoints ---
    op.create_table(
        "campaign_checkpoints",
        *_timestamp_columns(),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("checkpoint_data", postgresql.JSONB, nullable=False),
    )
    op.create_index("ix_campaign_checkpoints_campaign_id", "campaign_checkpoints", ["campaign_id"])
    op.create_index("ix_campaign_checkpoints_agent_name", "campaign_checkpoints", ["agent_name"])

    # --- keywords ---
    op.create_table(
        "keywords",
        *_timestamp_columns(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term", sa.String(500), nullable=False),
        sa.Column("search_volume", sa.Integer),
        sa.Column("difficulty", sa.Float),
        sa.Column("current_position", sa.Integer),
        sa.Column("target_position", sa.Integer),
        sa.Column("cluster", postgresql.JSONB),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_keywords_client_id", "keywords", ["client_id"])
    op.create_index("ix_keywords_term", "keywords", ["term"])

    # --- keyword_history ---
    op.create_table(
        "keyword_history",
        *_timestamp_columns(),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("date", sa.Date, nullable=False),
    )
    op.create_index("ix_keyword_history_keyword_id", "keyword_history", ["keyword_id"])
    op.create_index("ix_keyword_history_date", "keyword_history", ["date"])

    # --- contacts ---
    op.create_table(
        "contacts",
        *_timestamp_columns(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("first_name", sa.String(255)),
        sa.Column("last_name", sa.String(255)),
        sa.Column("segment_tags", postgresql.ARRAY(sa.String)),
        sa.Column("behavior_data", postgresql.JSONB),
        sa.Column("lead_score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True)),
        sa.Column("opted_out", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_contacts_client_id", "contacts", ["client_id"])
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_lead_score", "contacts", ["lead_score"])
    op.create_index("ix_contacts_opted_out", "contacts", ["opted_out"])

    # --- email_sequences ---
    email_sequence_status = postgresql.ENUM(
        "pending", "in_progress", "completed", "cancelled", name="email_sequence_status"
    )
    email_sequence_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "email_sequences",
        *_timestamp_columns(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_name", sa.String(100), nullable=False),
        sa.Column("current_step", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", email_sequence_status, nullable=False, server_default="pending"),
        sa.Column("triggered_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_email_sequences_client_id", "email_sequences", ["client_id"])
    op.create_index("ix_email_sequences_contact_id", "email_sequences", ["contact_id"])
    op.create_index("ix_email_sequences_sequence_name", "email_sequences", ["sequence_name"])
    op.create_index("ix_email_sequences_status", "email_sequences", ["status"])

    # --- content_templates ---
    op.create_table(
        "content_templates",
        *_timestamp_columns(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_type", sa.String(100), nullable=False),
        sa.Column("structure", postgresql.JSONB, nullable=False),
        sa.Column("figma_file_id", sa.String(255)),
        sa.Column("canva_template_id", sa.String(255)),
    )
    op.create_index("ix_content_templates_client_id", "content_templates", ["client_id"])
    op.create_index("ix_content_templates_template_type", "content_templates", ["template_type"])

    # --- contents ---
    content_type = postgresql.ENUM(
        "article", "post", "email", "landing_page", "visual", name="content_type"
    )
    content_type.create(op.get_bind(), checkfirst=True)
    content_platform = postgresql.ENUM(
        "linkedin", "meta", "tiktok", "email", "web", name="content_platform"
    )
    content_platform.create(op.get_bind(), checkfirst=True)
    content_status = postgresql.ENUM(
        "draft", "review", "published", "archived", name="content_status"
    )
    content_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "contents",
        *_timestamp_columns(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL")),
        sa.Column("agent_source", sa.String(100), nullable=False),
        sa.Column("content_type", content_type, nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("platform", content_platform, nullable=False),
        sa.Column("status", content_status, nullable=False, server_default="draft"),
        sa.Column("performance_data", postgresql.JSONB),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        # Ajouté au Prompt 7.1 (voir db/models/content.py).
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_contents_client_id", "contents", ["client_id"])
    op.create_index("ix_contents_campaign_id", "contents", ["campaign_id"])
    op.create_index("ix_contents_agent_source", "contents", ["agent_source"])
    op.create_index("ix_contents_content_type", "contents", ["content_type"])
    op.create_index("ix_contents_platform", "contents", ["platform"])
    op.create_index("ix_contents_status", "contents", ["status"])
    op.create_index("ix_contents_published_at", "contents", ["published_at"])
    op.create_index("ix_contents_scheduled_at", "contents", ["scheduled_at"])

    # --- performance_metrics ---
    op.create_table(
        "performance_metrics",
        *_timestamp_columns(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL")),
        sa.Column("channel", sa.String(100), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Float, nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_performance_metrics_client_id", "performance_metrics", ["client_id"])
    op.create_index("ix_performance_metrics_campaign_id", "performance_metrics", ["campaign_id"])
    op.create_index("ix_performance_metrics_channel", "performance_metrics", ["channel"])
    op.create_index("ix_performance_metrics_metric_name", "performance_metrics", ["metric_name"])
    op.create_index("ix_performance_metrics_period_start", "performance_metrics", ["period_start"])
    op.create_index("ix_performance_metrics_period_end", "performance_metrics", ["period_end"])

    # --- agent_decisions ---
    op.create_table(
        "agent_decisions",
        *_timestamp_columns(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("decision_type", sa.String(100), nullable=False),
        sa.Column("decision_data", postgresql.JSONB, nullable=False),
        sa.Column("outcome", postgresql.JSONB),
    )
    op.create_index("ix_agent_decisions_client_id", "agent_decisions", ["client_id"])
    op.create_index("ix_agent_decisions_agent_name", "agent_decisions", ["agent_name"])
    op.create_index("ix_agent_decisions_decision_type", "agent_decisions", ["decision_type"])

    # --- users ---
    user_role = postgresql.ENUM("admin", "manager", "viewer", name="user_role")
    user_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        *_timestamp_columns(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="viewer"),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_client_id", "users", ["client_id"])
    op.create_index("ix_users_is_active", "users", ["is_active"])

    # --- reports (Agent Reporting, Prompt 5.8) ---
    op.create_table(
        "reports",
        *_timestamp_columns(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("period", sa.String(50)),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("pdf_path", sa.String(500)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_reports_client_id", "reports", ["client_id"])
    op.create_index("ix_reports_report_type", "reports", ["report_type"])
    op.create_index("ix_reports_period", "reports", ["period"])

    # --- langgraph_checkpoints (schéma attendu par PostgresSaver de LangGraph) ---
    op.create_table(
        "langgraph_checkpoints",
        sa.Column("thread_id", sa.String(255), primary_key=True),
        sa.Column("checkpoint_id", sa.String(255), primary_key=True),
        sa.Column("parent_id", sa.String(255)),
        sa.Column("checkpoint_data", postgresql.JSONB, nullable=False),
        sa.Column("metadata", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("langgraph_checkpoints")
    op.drop_table("reports")
    op.drop_table("users")
    op.drop_table("agent_decisions")
    op.drop_table("performance_metrics")
    op.drop_table("contents")
    op.drop_table("content_templates")
    op.drop_table("email_sequences")
    op.drop_table("contacts")
    op.drop_table("keyword_history")
    op.drop_table("keywords")
    op.drop_table("campaign_checkpoints")
    op.drop_table("campaigns")
    op.drop_table("clients")

    bind = op.get_bind()
    for enum_name in (
        "user_role",
        "content_status",
        "content_platform",
        "content_type",
        "email_sequence_status",
        "campaign_status",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
