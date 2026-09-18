"""Outils Social : automatisation n8n, adaptation de contenu par plateforme."""

from backend.tools.social.content_adapter import (
    InstagramPost,
    LinkedInPost,
    TikTokPost,
    Tweet,
    adapt_for_instagram,
    adapt_for_linkedin,
    adapt_for_tiktok,
    adapt_for_twitter,
)
from backend.tools.social.n8n_client import (
    AVAILABLE_WORKFLOWS,
    WORKFLOW_LINKEDIN_POST,
    WORKFLOW_META_POST,
    WORKFLOW_SOCIAL_MENTIONS_MONITOR,
    WORKFLOW_SOCIAL_METRICS_COLLECT,
    WORKFLOW_TIKTOK_POST,
    ExecutionStatus,
    N8nClient,
    Workflow,
    WorkflowExecution,
)

__all__ = [
    "N8nClient",
    "WorkflowExecution",
    "ExecutionStatus",
    "Workflow",
    "WORKFLOW_LINKEDIN_POST",
    "WORKFLOW_META_POST",
    "WORKFLOW_TIKTOK_POST",
    "WORKFLOW_SOCIAL_METRICS_COLLECT",
    "WORKFLOW_SOCIAL_MENTIONS_MONITOR",
    "AVAILABLE_WORKFLOWS",
    "LinkedInPost",
    "InstagramPost",
    "TikTokPost",
    "Tweet",
    "adapt_for_linkedin",
    "adapt_for_instagram",
    "adapt_for_tiktok",
    "adapt_for_twitter",
]
