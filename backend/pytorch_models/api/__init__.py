"""API FastAPI du service pytorch_models : expose les modèles internes
(classification, embeddings, scoring, anomalies) aux autres services NEXUS AI.

Sous-dossier absent du scaffold initial (Prompt 1.1, qui ne listait que
classifiers/, embeddings/, scoring/, anomaly/)  ajouté au Prompt 3.2 pour
router_service.py.
"""

from backend.pytorch_models.api.router_service import app

__all__ = ["app"]
