"""Observabilité centralisée : tracing LangFuse, gestion de prompts, évaluateurs de qualité, métriques Prometheus.

`metrics_exporter` n'est PAS réexporté ici (contrairement aux autres
sous-modules) : c'est le seul à importer `prometheus_client` au niveau
module (pas en lazy import, contrairement au reste de ce package)  un
simple `from backend.core.monitoring import NexusTracer` ne doit pas
imposer cette dépendance à qui n'a besoin que du tracing. Importer
explicitement `backend.core.monitoring.metrics_exporter` pour l'utiliser."""

from backend.core.monitoring.evaluators import evaluate_ad_copy, evaluate_content_quality, evaluate_email_subject, send_evaluation_to_langfuse
from backend.core.monitoring.langfuse_callbacks import NexusLangFuseCallback
from backend.core.monitoring.langfuse_tracer import NexusTracer, trace_agent
from backend.core.monitoring.prompt_manager import PromptInfo, get_prompt, list_prompts, update_prompt

__all__ = [
    "NexusTracer",
    "trace_agent",
    "NexusLangFuseCallback",
    "get_prompt",
    "update_prompt",
    "list_prompts",
    "PromptInfo",
    "evaluate_content_quality",
    "evaluate_email_subject",
    "evaluate_ad_copy",
    "send_evaluation_to_langfuse",
]
