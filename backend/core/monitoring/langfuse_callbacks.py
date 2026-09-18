"""Callback LangChain/LangGraph pour le tracing automatique  Prompt 6.2.

Distinct de l'intégration LangFuse déjà présente dans `litellm_config.py`
(Prompt 3.1) : celle-ci trace les appels PROVIDER LLM (peu importe l'agent
qui les déclenche), tandis que `NexusLangFuseCallback` ci-dessous trace
l'EXÉCUTION DU GRAPHE LangGraph lui-même (chaînes/nœuds, outils)  deux
couches d'instrumentation complémentaires, pas redondantes. À passer dans
`config={"callbacks": [NexusLangFuseCallback()]}` de `graph.astream()`/
`.ainvoke()`, même mécanisme que les callbacks déjà utilisés ailleurs dans
ce projet (ex. `llm_client.py`).

Renommage : le spec demande `LIDIALangFuseCallback`  LIDIA renommé NEXUS AI
(voir `llm_client.NexusLLMClient`) ; cette classe s'appelle donc
`NexusLangFuseCallback`.

Chaque run LangChain identifie ses spans par `run_id` (UUID fourni par
LangChain à chaque callback)  un dict `{run_id: observation}` fait le lien
entre le cycle de vie LangChain (`on_X_start`/`on_X_end`) et celui de
LangFuse (`start_observation(...)` puis `.end()`), avec `parent_run_id` pour
imbriquer les spans (chaîne parente -> outil enfant, etc.) plutôt que de
créer des traces plates sans hiérarchie."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = structlog.get_logger(__name__)


class NexusLangFuseCallback(BaseCallbackHandler):
    def __init__(self) -> None:
        super().__init__()
        self._client = self._safe_client()
        self._observations: dict[UUID, Any] = {}

    @staticmethod
    def _safe_client():
        try:
            from backend.config.logging import get_langfuse_client

            return get_langfuse_client()
        except Exception as exc:
            logger.debug("langfuse_callbacks.client_unavailable", error=str(exc))
            return None

    def _parent_observation(self, parent_run_id: UUID | None):
        if parent_run_id is not None and parent_run_id in self._observations:
            return self._observations[parent_run_id]
        return self._client

    def _start(self, run_id: UUID, parent_run_id: UUID | None, *, name: str, as_type: str, **kwargs: Any) -> None:
        if self._client is None:
            return
        try:
            parent = self._parent_observation(parent_run_id)
            observation = parent.start_observation(name=name, as_type=as_type, **kwargs)
            self._observations[run_id] = observation
        except Exception as exc:
            logger.warning("langfuse_callbacks.start_observation_failed", name=name, error=str(exc))

    def _end(self, run_id: UUID, **update_kwargs: Any) -> None:
        observation = self._observations.pop(run_id, None)
        if observation is None:
            return
        try:
            observation.update(**update_kwargs)
            observation.end()
        except Exception as exc:
            logger.warning("langfuse_callbacks.end_observation_failed", error=str(exc))

    # ── LLM ──────────────────────────────────────────────────────────────

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *, run_id: UUID, parent_run_id: UUID | None = None, tags=None, metadata=None, **kwargs: Any
    ) -> None:
        model = (serialized or {}).get("kwargs", {}).get("model") or (serialized or {}).get("id", ["unknown"])[-1]
        self._start(run_id, parent_run_id, name="llm_call", as_type="generation", input=prompts, model=str(model), metadata=metadata)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        try:
            completions = [g[0].text for g in response.generations if g]
        except Exception:
            completions = None
        usage = (response.llm_output or {}).get("token_usage") if response.llm_output else None
        self._end(run_id, output=completions, usage_details=usage)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._end(run_id, level="ERROR", status_message=str(error))

    # ── Chaînes (nœuds LangGraph) ────────────────────────────────────────

    def on_chain_start(
        self, serialized: dict[str, Any], inputs: dict[str, Any], *, run_id: UUID, parent_run_id: UUID | None = None, tags=None, metadata=None, **kwargs: Any
    ) -> None:
        name = (serialized or {}).get("name") or (serialized or {}).get("id", ["chain"])[-1]
        self._start(run_id, parent_run_id, name=str(name), as_type="chain", input=inputs, metadata=metadata)

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._end(run_id, output=outputs)

    # ── Outils (tools) ───────────────────────────────────────────────────

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, parent_run_id: UUID | None = None, tags=None, metadata=None, inputs=None, **kwargs: Any
    ) -> None:
        name = (serialized or {}).get("name", "tool")
        self._start(run_id, parent_run_id, name=str(name), as_type="tool", input=inputs or input_str, metadata=metadata)

    def on_tool_end(self, output: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> None:
        self._end(run_id, output=output)


__all__ = ["NexusLangFuseCallback"]
