"""Worker pour les tâches LLM  Prompt 6.1.

Chaque tâche Celery est synchrone par nature (protocole du worker) mais pilote
du code async (graphes LangGraph, `NexusLLMClient`)  `asyncio.run()` à
l'intérieur de chaque tâche, pattern déjà établi ailleurs dans ce projet pour
les mêmes raisons (ex. `dashboard/scan_router.py` côté SecurBench, même
contrainte). Une nouvelle boucle d'événement par exécution de tâche est
correcte ici : chaque worker Celery traite les tâches une par une (pas de
boucle partagée à gérer entre tâches).
"""

import asyncio

import structlog

from backend.config.settings import settings
from backend.tasks.celery_app import celery_app, default_priority_for_queue
from backend.tasks.queues.redis_queue import QUEUE_LLM

logger = structlog.get_logger(__name__)

# Priorité kombu par défaut pour cette queue  voir celery_app.py pour la
# preuve de l'inversion business->kombu. Sans ce `priority=` au niveau du
# décorateur, `Task.apply_async`/`.delay()` retombe sur
# `task_default_priority` (config globale), pas sur la priorité PAR QUEUE du
# spec : chaque appel `.delay()` de ce fichier passerait alors la même
# priorité neutre, quelle que soit sa queue nominale (constaté en
# construisant ce fichier  vérifié dans `Task.apply_async` :
# `if self.priority: options.setdefault('priority', self.priority)`).
_LLM_PRIORITY = default_priority_for_queue(QUEUE_LLM)

# Modèle de repli plus rapide (alias Router LiteLLM, voir litellm_config.py)
# utilisé par le retry TimeoutError  un modèle "cheap"/"fast" répond plus
# vite qu'un modèle "default", quitte à sacrifier un peu de qualité pour ne
# pas rater le budget de temps de la tâche.
_FAST_RETRY_MODEL_ALIAS = "fast"


def _instrumented_span(task_name: str):
    """Contexte LangFuse best-effort pour une tâche Celery  instrumentation
    minimale en attendant `core/monitoring/langfuse_tracer.py` (Prompt 6.2,
    pas encore construit dans ce projet), qui centralisera ce mécanisme pour
    tous les workers plutôt que de le dupliquer. Dégrade en no-op silencieux
    si LangFuse n'est pas configuré/joignable  jamais bloquant pour la tâche."""
    try:
        from langfuse import get_client

        return get_client().start_as_current_span(name=task_name)
    except Exception:
        from contextlib import nullcontext

        return nullcontext()


def _extract_prompt_reduction(state_dict: dict) -> dict:
    """Réduit heuristiquement la taille d'un `state_dict` avant un retry
    ContextLengthError : tronque les listes de texte les plus volumineuses
    (candidats, endpoints, contenus similaires...) de moitié plutôt que de
    lever à nouveau avec exactement la même entrée trop longue."""
    reduced = dict(state_dict)
    for key, value in list(reduced.items()):
        if isinstance(value, list) and len(value) > 4:
            reduced[key] = value[: len(value) // 2]
        elif isinstance(value, str) and len(value) > 2000:
            reduced[key] = value[:1000]
    return reduced


# ── Registre des graphes agents (lazy) ──────────────────────────────────────

_AGENT_GRAPH_BUILDERS: dict[str, str] = {
    "seo": "backend.agents.seo.graph:build_seo_graph",
    "sea": "backend.agents.sea.graph:build_sea_graph",
    "content": "backend.agents.content.graph:build_content_graph",
    "social": "backend.agents.social.graph:build_social_graph",
    "email": "backend.agents.email.graph:build_email_graph",
    "analytics": "backend.agents.analytics.graph:build_analytics_graph",
    "creative": "backend.agents.creative.graph:build_creative_graph",
    "reporting": "backend.agents.reporting.graph:build_reporting_graph",
}


def _resolve_graph_builder(agent_name: str):
    spec = _AGENT_GRAPH_BUILDERS.get(agent_name)
    if spec is None:
        raise ValueError(f"agent_name inconnu : {agent_name!r}. Valides : {sorted(_AGENT_GRAPH_BUILDERS)}")
    module_path, func_name = spec.split(":")
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, func_name)


@celery_app.task(
    bind=True,
    name="nexus.llm.run_agent_task",
    queue=QUEUE_LLM,
    priority=_LLM_PRIORITY,
    max_retries=3,
)
def run_agent_task(self, agent_name: str, state_dict: dict, thread_id: str) -> dict:
    """Exécute un sous-graphe d'agent LangGraph de manière asynchrone
    (worker Celery), avec la stratégie de retry intelligent du spec."""
    import litellm

    with _instrumented_span(f"run_agent_task:{agent_name}"):
        try:
            build_graph = _resolve_graph_builder(agent_name)
            graph = build_graph()
            result = asyncio.run(graph.ainvoke(state_dict, config={"configurable": {"thread_id": thread_id}}))
            logger.info("llm_worker.agent_task_completed", agent_name=agent_name, thread_id=thread_id)
            return result
        except litellm.RateLimitError as exc:
            logger.warning("llm_worker.rate_limited_retrying", agent_name=agent_name, error=str(exc))
            raise self.retry(exc=exc, countdown=60)
        except litellm.ContextWindowExceededError as exc:
            logger.warning("llm_worker.context_exceeded_reducing_prompt", agent_name=agent_name, error=str(exc))
            reduced_state = _extract_prompt_reduction(state_dict)
            raise self.retry(exc=exc, countdown=5, kwargs={"agent_name": agent_name, "state_dict": reduced_state, "thread_id": thread_id})
        except litellm.Timeout as exc:
            logger.warning("llm_worker.timeout_retrying_fast_model", agent_name=agent_name, error=str(exc))
            state_with_fast_model = {**state_dict, "_force_model_alias": _FAST_RETRY_MODEL_ALIAS}
            raise self.retry(exc=exc, countdown=10, kwargs={"agent_name": agent_name, "state_dict": state_with_fast_model, "thread_id": thread_id})


@celery_app.task(bind=True, name="nexus.llm.generate_content_task", queue=QUEUE_LLM, priority=_LLM_PRIORITY, max_retries=3)
def generate_content_task(self, brief: dict, client_id: str) -> dict:
    """Génère un contenu via l'Agent Content  sérialise le premier
    `generated_contents` produit (`Content.model_dump(mode="json")`), pas le
    graphe entier (le spec attend `→ Content`, pas l'état complet)."""
    import litellm

    from backend.agents.content.graph import build_content_graph

    with _instrumented_span("generate_content_task"):
        try:
            graph = build_content_graph()
            initial_state = {
                "client_id": client_id,
                "contents": [],
                "brief": brief,
                "editorial_guidelines": None,
                "similar_contents": [],
                "selected_template": None,
                "draft": None,
                "iterations": 0,
                "max_iterations": 3,
                "quality_evaluation": None,
                "seo_score": None,
                "final_content": None,
                "needs_human_review": False,
                "stored_content_id": None,
                "generated_contents": [],
            }
            result = asyncio.run(graph.ainvoke(initial_state))
            contents = result.get("generated_contents") or []
            if not contents:
                raise RuntimeError("generate_content_task : aucun contenu produit par l'Agent Content.")
            content = contents[0]
            payload = content.model_dump(mode="json") if hasattr(content, "model_dump") else content
            logger.info("llm_worker.content_generated", client_id=client_id)
            return payload
        except litellm.RateLimitError as exc:
            logger.warning("llm_worker.generate_content_rate_limited", client_id=client_id, error=str(exc))
            raise self.retry(exc=exc, countdown=60)
        except litellm.Timeout as exc:
            logger.warning("llm_worker.generate_content_timeout", client_id=client_id, error=str(exc))
            raise self.retry(exc=exc, countdown=10)


@celery_app.task(name="nexus.llm.classify_task_complexity_task", queue=QUEUE_LLM, priority=_LLM_PRIORITY)
def classify_task_complexity_task(task_description: str) -> str:
    """Appelle le service PyTorch (`/classify`, voir pytorch_models/api/
    router_service.py  ajouté au Prompt 6.1, `/route` seul retournait une
    décision de routage complète, pas la complexité isolée que ce worker
    demande)."""
    import httpx

    with httpx.Client(base_url=settings.PYTORCH_MODELS_URL, timeout=15.0) as client:
        response = client.post("/classify", json={"task_description": task_description})
        response.raise_for_status()
        complexity = response.json()["complexity"]

    logger.info("llm_worker.task_complexity_classified", complexity=complexity)
    return complexity


__all__ = ["run_agent_task", "generate_content_task", "classify_task_complexity_task"]
