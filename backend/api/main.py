"""Application FastAPI principale  Prompt 7.1.

`MainGraph.create()` (backend/core/graph/main_graph.py, Prompt 4.3) est
construit UNE FOIS ici, au démarrage, et stocké sur `app.state.main_graph` 
c'est ce même objet que `routes/campaigns.py` et `routes/hitl.py`
consultent via `request.app.state.main_graph`. Son checkpointer
PostgresSaver reste ouvert pour toute la durée de vie du process, fermé
proprement à l'arrêt (`aclose()`).

"charger les modèles PyTorch" (spec) : les modèles PyTorch sont chargés par
le SERVICE `pytorch_models` lui-même, dans SON PROPRE lifespan (voir
backend/pytorch_models/api/router_service.py)  un processus Docker
distinct (port 8001, voir docker-compose.yml). Cette API-ci ne peut pas
"charger" un modèle qui vit dans un autre process ; le startup ci-dessous
vérifie donc que ce service est joignable et prêt (health-check HTTP), pas
qu'un modèle est rechargé en mémoire ici.

Migrations Alembic : `alembic.command.upgrade` exécute lui-même un
`asyncio.run()` interne (voir db/migrations/env.py, `run_migrations_online`)
 l'appeler directement depuis cette coroutine de lifespan lèverait
`RuntimeError: asyncio.run() cannot be called from a running event loop`
(uvicorn fait déjà tourner une boucle). D'où `asyncio.to_thread` : exécute
l'appel synchrone dans un thread séparé, qui peut ouvrir sa propre boucle
sans conflit.
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api import auth
from backend.api.routes import (
    agents,
    analytics,
    campaigns,
    clients,
    content,
    hitl,
    users,
)
from backend.api.routes import settings as settings_routes
from backend.api.sse import streams as sse_streams
from backend.api.websocket import handlers as ws_handlers
from backend.api.websocket.agent_broadcaster import get_agent_broadcaster
from backend.api.websocket.connection_manager import get_connection_manager
from backend.config.logging import get_langfuse_client, setup_logging
from backend.config.settings import settings
from backend.core.graph.main_graph import MainGraph
from backend.core.memory.qdrant_client import get_qdrant_client
from backend.core.memory.redis_client import get_redis_client
from backend.core.monitoring.metrics_exporter import metrics_router, registry
from backend.db.session import engine
from backend.tasks.queues.task_monitor import QueueMetricsCollector

setup_logging()
logger = structlog.get_logger(__name__)


def _run_alembic_upgrade_sync() -> None:
    from alembic import command
    from alembic.config import Config

    alembic_ini = Path(__file__).resolve().parents[1] / "db" / "migrations" / "alembic.ini"
    cfg = Config(str(alembic_ini))
    command.upgrade(cfg, "head")


async def _check_pytorch_models_service() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(base_url=settings.PYTORCH_MODELS_URL, timeout=5.0) as client:
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        raise RuntimeError(f"service pytorch_models injoignable ({settings.PYTORCH_MODELS_URL}) : {exc}") from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("main.startup_begin")

    await asyncio.to_thread(_run_alembic_upgrade_sync)
    logger.info("main.migrations_applied")

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    logger.info("main.database_connected")

    redis_client = get_redis_client()
    if not await redis_client.health_check():
        logger.warning("main.redis_unreachable_at_startup")

    qdrant_client = get_qdrant_client()
    await qdrant_client.ensure_collections()
    logger.info("main.qdrant_collections_ready")

    try:
        pytorch_status = await _check_pytorch_models_service()
        logger.info("main.pytorch_models_service_ready", detail=pytorch_status)
    except Exception as exc:
        logger.warning("main.pytorch_models_service_unreachable", error=str(exc))

    langfuse_client = get_langfuse_client()
    try:
        auth_ok = await asyncio.to_thread(langfuse_client.auth_check)
        logger.info("main.langfuse_initialized", auth_ok=auth_ok)
    except Exception as exc:
        logger.warning("main.langfuse_auth_check_failed", error=str(exc))

    # Collecteur custom des queues Celery (Prompt 6.1) sur le même registre
    # que les métriques LLM/agents (Prompt 6.2)  exposé par un seul
    # endpoint /metrics ci-dessous plutôt que deux.
    registry.register(QueueMetricsCollector())

    main_graph = await MainGraph.create()
    app.state.main_graph = main_graph
    app.state.redis_client = redis_client
    app.state.qdrant_client = qdrant_client
    app.state.langfuse_client = langfuse_client

    # WebSocket/SSE (Prompt 7.2) : le gestionnaire de connexions démarre ses
    # boucles de fond (abonnement Pub/Sub cross-instance + heartbeat) ; le
    # diffuseur d'agents s'abonne au flux d'événements Celery réel.
    connection_manager = get_connection_manager()
    await connection_manager.start()
    agent_broadcaster = get_agent_broadcaster()
    agent_broadcaster.subscribe_to_langgraph_events()
    agent_broadcaster.subscribe_to_celery_events()
    app.state.connection_manager = connection_manager
    app.state.agent_broadcaster = agent_broadcaster

    logger.info("main.startup_complete")
    yield

    logger.info("main.shutdown_begin")
    agent_broadcaster.stop_celery_capture()
    await connection_manager.stop()
    await main_graph.aclose()
    await redis_client.close()
    await qdrant_client.close()
    logger.info("main.shutdown_complete")


app = FastAPI(title="NEXUS AI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# minimum_size=1000 : ne compresse pas les réponses minuscules (le gain
# n'en vaut pas le coût CPU)  seuil usuel de Starlette/FastAPI pour ce middleware.
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def logging_and_trace_id_middleware(request: Request, call_next):
    """Trace_id : repris de l'en-tête entrant si le client en fournit un
    (corrélation cross-service), sinon généré ici  toujours réinjecté dans
    la réponse (spec : "injection du trace_id dans les headers")."""
    trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    response.headers["X-Trace-Id"] = trace_id
    logger.info(
        "http.request",
        ctx_trace_id=trace_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response


def _error_payload(status_code: int, message: str, *, details: Any = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"status_code": status_code, "message": message, "details": details}})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_payload(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_payload(status.HTTP_422_UNPROCESSABLE_ENTITY, "Erreur de validation.", details=exc.errors())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("http.unhandled_exception", path=request.url.path, error=str(exc), exc_info=exc)
    return _error_payload(status.HTTP_500_INTERNAL_SERVER_ERROR, "Erreur interne du serveur.")


app.include_router(auth.router)
app.include_router(campaigns.router)
app.include_router(agents.router)
app.include_router(hitl.router)
app.include_router(content.router)
app.include_router(analytics.router)
app.include_router(settings_routes.router)
app.include_router(users.router)
app.include_router(clients.router)
app.include_router(ws_handlers.router)
app.include_router(sse_streams.router)
app.include_router(metrics_router)


@app.get("/health")
async def health() -> dict[str, Any]:
    components: dict[str, str] = {}

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception as exc:
        components["database"] = f"error: {exc}"

    components["redis"] = "ok" if await get_redis_client().health_check() else "error"
    components["qdrant"] = "ok" if await get_qdrant_client().health_check() else "error"

    try:
        await _check_pytorch_models_service()
        components["pytorch_models"] = "ok"
    except Exception as exc:
        components["pytorch_models"] = f"error: {exc}"

    overall = "ok" if all(value == "ok" for value in components.values()) else "degraded"
    return {"status": overall, "components": components}


__all__ = ["app"]
