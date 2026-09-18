"""Repositories encapsulant les accès en base de données par entité métier."""

from backend.db.repositories.audience_repository import ContactRepository, EmailSequenceRepository
from backend.db.repositories.base_repository import BaseRepository
from backend.db.repositories.campaign_repository import (
    CampaignCheckpointRepository,
    CampaignRepository,
)
from backend.db.repositories.client_repository import ClientRepository
from backend.db.repositories.content_repository import ContentRepository, ContentTemplateRepository
from backend.db.repositories.keyword_repository import KeywordHistoryRepository, KeywordRepository
from backend.db.repositories.langgraph_checkpoint_repository import LangGraphCheckpointRepository
from backend.db.repositories.performance_repository import (
    AgentDecisionRepository,
    PerformanceMetricRepository,
)
from backend.db.repositories.user_repository import UserRepository

__all__ = [
    "BaseRepository",
    "ClientRepository",
    "CampaignRepository",
    "CampaignCheckpointRepository",
    "ContentRepository",
    "ContentTemplateRepository",
    "KeywordRepository",
    "KeywordHistoryRepository",
    "ContactRepository",
    "EmailSequenceRepository",
    "PerformanceMetricRepository",
    "AgentDecisionRepository",
    "UserRepository",
    "LangGraphCheckpointRepository",
]
