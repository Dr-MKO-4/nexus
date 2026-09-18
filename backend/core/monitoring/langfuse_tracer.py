"""Traceur LangFuse centralisé  Prompt 6.2.

Écarts corrigés par rapport à la spec initiale (vérifiés contre le SDK
réellement installé, `langfuse==4.15.2`, par inspection directe des
signatures  pas supposés) :

1. **Aucune classe `Trace`/`Span` au sens du spec.** Le SDK v2 (API
   `start_trace`/`start_span` retournant des objets `Trace`/`Span` dédiés) a
   été entièrement remplacé en v3+ par un modèle basé OpenTelemetry :
   `client.start_observation(name=..., as_type=...)` retourne directement un
   objet observation (`LangfuseSpan`/`LangfuseGeneration`/...), qui EST à la
   fois la trace racine (si sans parent) et le span lui-même. `start_trace`
   et `start_span` ci-dessous retournent donc le même type d'objet  la
   distinction "Trace" vs "Span" du spec n'existe plus dans le SDK, mais
   l'API de ce module la préserve en surface (deux méthodes séparées) pour
   rester fidèle aux noms demandés.
2. **`score_trace(trace_id, name, value, comment)` correspond à
   `client.create_score(trace_id=..., name=..., value=..., comment=...)`**,
   pas à `score_current_trace` (qui score la trace du contexte OTel courant,
   pas une trace arbitraire par id  `log_hitl_event`/`score_trace` doivent
   pouvoir cibler une trace précise, potentiellement créée plus tôt dans un
   autre contexte d'exécution).
3. **`@trace_agent(name, agent_type)` s'appuie sur `langfuse.observe`**, le
   décorateur natif du SDK (vérifié : gère sync/async, capture input/output,
   propage le contexte OTel)  `agent_type` n'est pas un paramètre de
   `observe()` (qui n'accepte qu'un `as_type` de vocabulaire fixe :
   "agent"/"tool"/"chain"/...) : fixé à `as_type="agent"`, `agent_type` (la
   VALEUR métier NEXUS AI - "seo", "sea", "content"...) est injecté comme
   métadonnée de l'observation via une mise à jour post-exécution.
4. **Réutilise `backend.config.logging.get_langfuse_client()`** (déjà
   l'initialisation "depuis settings" exigée par le point 1 du spec, écrite
   au Prompt 2.x) plutôt que de dupliquer la construction de `Langfuse(...)`.
5. Renommage : le spec demande une classe `LIDIATracer`  LIDIA a été
   renommé NEXUS AI plus tôt dans le projet (voir `llm_client.NexusLLMClient`
   pour le même renommage déjà appliqué) ; cette classe s'appelle donc
   `NexusTracer`.

Tout est défensif : si LangFuse n'est pas configuré/joignable, chaque
méthode dégrade en no-op silencieux (retourne `None`) plutôt que de lever 
l'observabilité ne doit jamais faire échouer un agent.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Literal, ParamSpec, TypeVar

import structlog

logger = structlog.get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

_AgentType = str  # valeur métier NEXUS AI libre ("seo", "sea", "content"...), pas un as_type LangFuse


def _safe_client():
    """`get_langfuse_client()` (voir config/logging.py) est sûr même sans
    configuration valide  vérifié par exécution réelle (log une erreur
    d'auth mais ne lève jamais)."""
    try:
        from backend.config.logging import get_langfuse_client

        return get_langfuse_client()
    except Exception as exc:
        logger.debug("langfuse_tracer.client_unavailable", error=str(exc))
        return None


class NexusTracer:
    """Traceur LangFuse centralisé pour les agents NEXUS AI."""

    def __init__(self) -> None:
        self._client = _safe_client()

    def start_trace(self, name: str, session_id: str | None = None, user_id: str | None = None, metadata: dict | None = None) -> Any | None:
        """Démarre une trace racine (aucun parent  voir écart n°1).
        Retourne l'observation LangFuse, ou `None` si indisponible.

        `session_id`/`user_id` : pas de paramètre dédié sur
        `start_observation` (vérifié par inspection de signature)  LangFuse
        les reconnaît comme des clés de métadonnées OTel réservées
        (`LangfuseOtelSpanAttributes.TRACE_SESSION_ID`/`TRACE_USER_ID`,
        `"session.id"`/`"user.id"`, vérifiées par inspection directe de la
        classe), fusionnées dans `metadata` plutôt que passées séparément."""
        if self._client is None:
            return None
        try:
            from langfuse import LangfuseOtelSpanAttributes

            merged_metadata = dict(metadata or {})
            if session_id:
                merged_metadata[LangfuseOtelSpanAttributes.TRACE_SESSION_ID] = session_id
            if user_id:
                merged_metadata[LangfuseOtelSpanAttributes.TRACE_USER_ID] = user_id

            return self._client.start_observation(name=name, as_type="span", metadata=merged_metadata or None)
        except Exception as exc:
            logger.warning("langfuse_tracer.start_trace_failed", name=name, error=str(exc))
            return None

    def start_span(self, trace: Any | None, name: str, input_data: Any = None) -> Any | None:
        """Démarre un span enfant de `trace` (ou une nouvelle trace racine
        si `trace` est `None`  dégradation utile plutôt qu'une exception)."""
        if self._client is None:
            return None
        try:
            parent = trace if trace is not None else self._client
            return parent.start_observation(name=name, as_type="span", input=input_data)
        except Exception as exc:
            logger.warning("langfuse_tracer.start_span_failed", name=name, error=str(exc))
            return None

    def end_span(self, span: Any | None, output_data: Any = None, usage: dict | None = None, model: str | None = None) -> None:
        if span is None:
            return
        try:
            span.update(output=output_data, usage_details=usage, model=model)
            span.end()
        except Exception as exc:
            logger.warning("langfuse_tracer.end_span_failed", error=str(exc))

    def log_generation(
        self,
        trace: Any | None,
        model: str,
        prompt: str,
        completion: str,
        tokens_used: dict | None = None,
        cost: float | None = None,
        latency: float | None = None,
    ) -> None:
        """Log une génération déjà terminée (pas pour un streaming en
        direct  `litellm_config.py` gère déjà le tracing temps réel des
        appels LLM via son propre callback LangFuse natif, voir Prompt 3.1 ;
        cette méthode sert aux générations hors du chemin LiteLLM standard,
        ex. appels directs à un provider)."""
        if self._client is None:
            return
        try:
            parent = trace if trace is not None else self._client
            generation = parent.start_observation(
                name="generation",
                as_type="generation",
                input=prompt,
                model=model,
                cost_details={"total": cost} if cost is not None else None,
                usage_details=tokens_used,
            )
            metadata = {"latency_seconds": latency} if latency is not None else None
            generation.update(output=completion, metadata=metadata)
            generation.end()
        except Exception as exc:
            logger.warning("langfuse_tracer.log_generation_failed", model=model, error=str(exc))

    def score_trace(self, trace_id: str, name: str, value: float, comment: str | None = None) -> None:
        """Score une trace par id  `client.create_score`, pas
        `score_current_trace` (voir écart n°2 en tête de fichier)."""
        if self._client is None:
            return
        try:
            self._client.create_score(trace_id=trace_id, name=name, value=value, comment=comment, data_type="NUMERIC")
        except Exception as exc:
            logger.warning("langfuse_tracer.score_trace_failed", trace_id=trace_id, name=name, error=str(exc))

    def log_hitl_event(self, trace: Any | None, agent: str, decision: str, context: dict | None = None) -> None:
        """Événement HITL (validation humaine)  `create_event`, un point
        instantané dans la trace (ni span ni génération, pas de durée)."""
        if self._client is None:
            return
        try:
            parent = trace if trace is not None else self._client
            parent.create_event(name="hitl_decision", input=context, metadata={"agent": agent, "decision": decision})
        except Exception as exc:
            logger.warning("langfuse_tracer.log_hitl_event_failed", agent=agent, decision=decision, error=str(exc))


def trace_agent(name: str, agent_type: _AgentType) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Décorateur pour instrumenter automatiquement une fonction d'agent 
    voir écart n°3 pour le détail de son adossement à `langfuse.observe`."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        try:
            from langfuse import observe
        except Exception:
            # LangFuse absent de l'environnement (extra optionnel, voir
            # requirements/base.txt) : décorateur transparent, pas bloquant.
            return func

        observed = observe(func, name=name, as_type="agent")

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            result = observed(*args, **kwargs)
            _tag_current_agent_type(agent_type)
            return result

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            result = await observed(*args, **kwargs)
            _tag_current_agent_type(agent_type)
            return result

        import asyncio

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper  # type: ignore[return-value]

    return decorator


def _tag_current_agent_type(agent_type: str) -> None:
    try:
        client = _safe_client()
        if client is not None:
            client.update_current_span(metadata={"agent_type": agent_type})
    except Exception:
        pass


__all__ = ["NexusTracer", "trace_agent"]
