"""Énumérations Python partagées par les modèles ORM.

Mappées en énumérations natives PostgreSQL par SQLAlchemy (`sa.Enum`),
ce qui contraint les valeurs au niveau base de données en plus du
typage Python.
"""

import enum


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    # Ajouté au Prompt 7.1 (DELETE /campaigns/{id} archive plutôt que
    # supprime la ligne  voir db/migrations/versions/0001_create_all_tables.py).
    ARCHIVED = "archived"


class ContentType(str, enum.Enum):
    ARTICLE = "article"
    POST = "post"
    EMAIL = "email"
    LANDING_PAGE = "landing_page"
    VISUAL = "visual"


class ContentPlatform(str, enum.Enum):
    LINKEDIN = "linkedin"
    META = "meta"
    TIKTOK = "tiktok"
    EMAIL = "email"
    WEB = "web"


class ContentStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class EmailSequenceStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"
