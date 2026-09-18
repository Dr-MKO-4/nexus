"""Outils Email : intégration Mautic (marketing automation)."""

from backend.tools.email.mautic_client import CampaignStats, Contact, EmailInteraction, ExecutionResult, MauticClient

__all__ = ["MauticClient", "Contact", "EmailInteraction", "ExecutionResult", "CampaignStats"]
