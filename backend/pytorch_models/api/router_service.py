"""Service FastAPI exposant HybridRouter via HTTP.

Déployé comme service Docker indépendant sur le port 8001 (voir
backend/Dockerfile.ml et docker-compose.yml, service pytorch_models) 
CMD par défaut de Dockerfile.ml : `uvicorn backend.pytorch_models.main:app`.
Ce module (`router_service.py`) fournit `app`, à monter depuis
`backend/pytorch_models/main.py` (pas encore créé  même situation que les
endpoints /embeddings/* documentés dans embedding_manager.py, Prompt 2.3).
"""

from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.llm.router.hybrid_router import HybridRouter, RoutingDecision
from backend.pytorch_models.classifiers.complexity_classifier import ComplexityClassifier

logger = structlog.get_logger(__name__)

# État du service en mémoire de process (mono-instance) : le classifieur
# n'est chargé qu'une fois au démarrage (lifespan), pas à chaque requête.
_state: dict[str, Any] = {
    "router": None,
    "classifier": None,
    "routes_served": 0,
    "routes_by_provider": {},
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    classifier = ComplexityClassifier.from_checkpoint()
    _state["classifier"] = classifier
    _state["router"] = HybridRouter(classifier=classifier)
    logger.info("router_service.started", model_trained=classifier.is_trained)
    yield
    logger.info("router_service.stopped")


app = FastAPI(title="NEXUS AI pytorch_models  router_service", lifespan=lifespan)


class RouteRequest(BaseModel):
    task_description: str
    task_type: str | None = None


@app.post("/route", response_model=RoutingDecision)
async def route(request: RouteRequest) -> RoutingDecision:
    router: HybridRouter | None = _state["router"]
    if router is None:
        raise HTTPException(status_code=503, detail="HybridRouter non initialisé")

    decision = await router.route(
        {"description": request.task_description, "task_type": request.task_type}
    )

    _state["routes_served"] += 1
    _state["routes_by_provider"][decision.provider] = (
        _state["routes_by_provider"].get(decision.provider, 0) + 1
    )
    return decision


@app.post("/classify")
async def classify(request: RouteRequest) -> dict[str, str]:
    """Complexité seule (simple/medium/complex), sans décision de routage
    complète  ajouté au Prompt 6.1 pour
    `tasks/workers/llm_worker.classify_task_complexity_task` : `/route`
    retourne un `RoutingDecision` entier (provider/modèle/coût/fallback),
    pas seulement la complexité que ce worker demande. Réutilise le même
    classifieur déjà chargé en mémoire (`_state["classifier"]`), pas une
    seconde instance."""
    classifier: ComplexityClassifier | None = _state["classifier"]
    if classifier is None:
        raise HTTPException(status_code=503, detail="ComplexityClassifier non initialisé")
    complexity = classifier.predict(request.task_description)
    return {"complexity": complexity}


@app.get("/health")
async def health() -> dict[str, Any]:
    classifier: ComplexityClassifier | None = _state["classifier"]
    return {
        "status": "ok" if classifier is not None else "not_ready",
        "model_loaded": classifier is not None,
        "model_trained": bool(classifier.is_trained) if classifier is not None else False,
    }


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    return {
        "routes_served": _state["routes_served"],
        "routes_by_provider": dict(_state["routes_by_provider"]),
    }
