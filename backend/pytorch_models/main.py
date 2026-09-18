"""Point d'entrée ASGI du service pytorch_models (port 8001, voir
docker-compose.yml et Dockerfile.ml : `CMD [..., "backend.pytorch_models.main:app", ...]`).

Fichier manquant jusqu'ici  `router_service.py` documentait déjà son
attente ("à monter depuis backend/pytorch_models/main.py, pas encore créé")
mais ce module n'existait pas : le service pytorch_models n'aurait pas pu
démarrer (`ModuleNotFoundError` sur `backend.pytorch_models.main`). Corrigé
en passant par Prompt 7.1 (API principale, qui appelle ce même service en
health-check au démarrage  voir backend/api/main.py)."""

from backend.pytorch_models.api.router_service import app

__all__ = ["app"]
