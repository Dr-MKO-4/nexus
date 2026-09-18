"""Modèles de scoring (qualité de contenu, performance prédictive de campagne, lead scoring)."""

from backend.pytorch_models.scoring.content_scorer import ContentScore, ContentScorer

__all__ = ["ContentScorer", "ContentScore"]

# Exports à venir (à compléter au fur et à mesure de l'implémentation) :
# from .campaign_scorer import CampaignScorer
