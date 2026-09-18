"""Modèles ORM représentant les entités métier (utilisateurs, campagnes, rapports, agents)."""

from backend.db.models.audiences import Contact, EmailSequence
from backend.db.models.base import Base, DeclarativeRoot
from backend.db.models.campaigns import Campaign, CampaignCheckpoint
from backend.db.models.clients import Client
from backend.db.models.content import Content, ContentTemplate
from backend.db.models.enums import (
    CampaignStatus,
    ContentPlatform,
    ContentStatus,
    ContentType,
    EmailSequenceStatus,
    UserRole,
)
from backend.db.models.keywords import Keyword, KeywordHistory
from backend.db.models.langgraph_checkpoints import LangGraphCheckpoint
from backend.db.models.performance import AgentDecision, PerformanceMetric
from backend.db.models.reports import Report
from backend.db.models.users import User

__all__ = [
    "Base",
    "DeclarativeRoot",
    "Campaign",
    "CampaignCheckpoint",
    "CampaignStatus",
    "Client",
    "Content",
    "ContentTemplate",
    "ContentType",
    "ContentPlatform",
    "ContentStatus",
    "Keyword",
    "KeywordHistory",
    "Contact",
    "EmailSequence",
    "EmailSequenceStatus",
    "PerformanceMetric",
    "AgentDecision",
    "Report",
    "User",
    "UserRole",
    "LangGraphCheckpoint",
]
