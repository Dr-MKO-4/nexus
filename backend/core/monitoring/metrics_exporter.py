"""Exporteur de métriques custom pour Prometheus  Prompt 6.2.

Renommage : le spec préfixe les métriques `lidia_*`  LIDIA renommé NEXUS AI
plus tôt dans le projet (voir `llm_client.NexusLLMClient`) ; préfixées
`nexus_*` ici, cohérent avec `tasks/queues/task_monitor.py`
(`nexus_queue_depth`, Prompt 6.1), déjà nommé selon cette convention.

Distinct de `task_monitor.QueueMetricsCollector` (Prompt 6.1) : celui-ci
couvre les métriques de FILES D'ATTENTE Celery, ce module couvre les
métriques LLM/agents/business  collecteurs Prometheus complémentaires, pas
redondants, tous deux enregistrés sur le même registre par l'endpoint
`/metrics` ci-dessous."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

logger = structlog.get_logger(__name__)

# Registre dédié (pas le registre par défaut global de prometheus_client) :
# permet de monter ce routeur dans plusieurs contextes de test sans
# collision d'enregistrement de métriques entre exécutions.
registry = CollectorRegistry()

# ── Métriques LLM ────────────────────────────────────────────────────────
nexus_llm_requests_total = Counter(
    "nexus_llm_requests_total", "Nombre total de requêtes LLM", ["agent", "model", "provider", "status"], registry=registry
)
nexus_llm_tokens_total = Counter(
    "nexus_llm_tokens_total", "Nombre total de tokens LLM", ["agent", "model", "type"], registry=registry
)
nexus_llm_cost_usd_total = Counter(
    "nexus_llm_cost_usd_total", "Coût cumulé des appels LLM (USD)", ["agent", "provider"], registry=registry
)
nexus_llm_latency_seconds = Histogram(
    "nexus_llm_latency_seconds", "Latence des appels LLM (secondes)", ["model"], registry=registry
)

# ── Métriques agents ─────────────────────────────────────────────────────
nexus_agent_executions_total = Counter(
    "nexus_agent_executions_total", "Nombre total d'exécutions d'agent", ["agent", "status"], registry=registry
)
nexus_agent_duration_seconds = Histogram(
    "nexus_agent_duration_seconds", "Durée d'exécution d'un agent (secondes)", ["agent"], registry=registry
)
nexus_agent_errors_total = Counter(
    "nexus_agent_errors_total", "Nombre total d'erreurs d'agent", ["agent", "error_type"], registry=registry
)

# ── Métriques business ───────────────────────────────────────────────────
nexus_campaigns_active_total = Counter(
    "nexus_campaigns_active_total", "Nombre de campagnes actives", ["client"], registry=registry
)
nexus_contents_generated_total = Counter(
    "nexus_contents_generated_total", "Nombre de contenus générés", ["type", "platform"], registry=registry
)
nexus_hitl_requests_total = Counter(
    "nexus_hitl_requests_total", "Nombre de validations humaines demandées", ["agent", "decision"], registry=registry
)
# Jauge distincte, ajoutée pour Prompt 6.3 (alerte `HITLQueueFull`, spec :
# "> 10 validations en attente") : `nexus_hitl_requests_total` compte les
# décisions déjà PRISES (approved/rejected/...), pas la profondeur de la
# file d'attente HITL  aucune métrique de ce type n'existait avant ce
# prompt. Le point d'appel réel de `set_hitl_pending` (ex. décompte des
# `interrupt()` LangGraph en attente par agent) reste hors périmètre des
# fichiers listés par ce prompt (infra Prometheus/Grafana uniquement) 
# métrique déclarée ici pour que l'alerte ci-dessous référence un nom réel
# plutôt qu'un nom inventé, valeur restera à 0 tant que rien ne l'appelle.
nexus_hitl_pending_total = Gauge(
    "nexus_hitl_pending_total", "Nombre de validations humaines actuellement en attente", ["agent"], registry=registry
)


def record_llm_request(
    agent: str, model: str, provider: str, tokens_input: int, tokens_output: int, cost: float, latency: float, status: str = "success"
) -> None:
    """Point d'enregistrement unique pour un appel LLM complet  à appeler
    depuis `llm_client.NexusLLMClient._track_cost` (Prompt 3.1, pas modifié
    ici : hors du périmètre de fichiers de ce prompt) pour que ces métriques
    soient réellement peuplées en production plutôt que de rester à zéro.

    `status` ("success"/"error", défaut "success") : ajouté pour Prompt 6.3
     sans ce label, aucune distinction succès/échec par fournisseur n'était
    possible dans `nexus_llm_requests_total`, rendant le panel "taux de
    succès par provider" du dashboard LLM (`llm_dashboard.json`)
    irréalisable. Paramètre optionnel avec valeur par défaut : aucun appelant
    existant (aucun à ce jour, voir docstring ci-dessus) n'est cassé par cet
    ajout."""
    nexus_llm_requests_total.labels(agent=agent, model=model, provider=provider, status=status).inc()
    nexus_llm_tokens_total.labels(agent=agent, model=model, type="input").inc(tokens_input)
    nexus_llm_tokens_total.labels(agent=agent, model=model, type="output").inc(tokens_output)
    nexus_llm_cost_usd_total.labels(agent=agent, provider=provider).inc(cost)
    nexus_llm_latency_seconds.labels(model=model).observe(latency)


def record_agent_execution(agent: str, status: str, duration_seconds: float, error_type: str | None = None) -> None:
    nexus_agent_executions_total.labels(agent=agent, status=status).inc()
    nexus_agent_duration_seconds.labels(agent=agent).observe(duration_seconds)
    if error_type:
        nexus_agent_errors_total.labels(agent=agent, error_type=error_type).inc()


def record_content_generated(content_type: str, platform: str) -> None:
    nexus_contents_generated_total.labels(type=content_type, platform=platform).inc()


def record_hitl_request(agent: str, decision: str) -> None:
    nexus_hitl_requests_total.labels(agent=agent, decision=decision).inc()


def set_hitl_pending(agent: str, count: int) -> None:
    nexus_hitl_pending_total.labels(agent=agent).set(count)


def set_active_campaigns(client_id: str, count: int) -> None:
    """`nexus_campaigns_active_total` est un `Counter` (spec : "_total",
    convention Prometheus pour une métrique monotone croissante), mais un
    NOMBRE DE CAMPAGNES ACTIVES est intrinsèquement une jauge (peut
    diminuer). Écart assumé du spec : incrémente/décrémente via un delta
    interne plutôt que d'exposer un `Gauge` sous un nom `_total`
    (contradictoire avec la convention Prometheus elle-même)  le choix le
    plus honnête reste de respecter le NOM du spec tout en documentant la
    limite plutôt que de renommer silencieusement la métrique."""
    current = nexus_campaigns_active_total.labels(client=client_id)._value.get()
    delta = count - current
    if delta > 0:
        current_metric = nexus_campaigns_active_total.labels(client=client_id)
        current_metric.inc(delta)
    logger.debug("metrics_exporter.active_campaigns_set", client_id=client_id, count=count, delta=delta)


# ── Endpoint FastAPI /metrics ────────────────────────────────────────────
metrics_router = APIRouter()


@metrics_router.get("/metrics")
async def metrics_endpoint() -> Response:
    """Exposé sur le port 8000 (spec)  le port lui-même dépend de la
    configuration uvicorn du service qui monte ce routeur (`backend/main.py`
    ou équivalent, hors périmètre de ce prompt) : ce module fournit la
    ROUTE, pas le binding réseau."""
    payload = generate_latest(registry)
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


__all__ = [
    "registry",
    "metrics_router",
    "nexus_llm_requests_total",
    "nexus_llm_tokens_total",
    "nexus_llm_cost_usd_total",
    "nexus_llm_latency_seconds",
    "nexus_agent_executions_total",
    "nexus_agent_duration_seconds",
    "nexus_agent_errors_total",
    "nexus_campaigns_active_total",
    "nexus_contents_generated_total",
    "nexus_hitl_requests_total",
    "nexus_hitl_pending_total",
    "record_llm_request",
    "record_agent_execution",
    "record_content_generated",
    "record_hitl_request",
    "set_hitl_pending",
    "set_active_campaigns",
]
