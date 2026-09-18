"""Outils SEA : intégrations Google Ads / Meta Ads pour la gestion des campagnes payantes."""

from backend.tools.sea.google_ads import CampaignPerformance, CampaignPerformanceRow, GoogleAdsClient, KeywordPerformance
from backend.tools.sea.meta_ads import AudienceData, InsightsData, MetaAdsClient

__all__ = [
    "GoogleAdsClient",
    "CampaignPerformance",
    "CampaignPerformanceRow",
    "KeywordPerformance",
    "MetaAdsClient",
    "InsightsData",
    "AudienceData",
]
