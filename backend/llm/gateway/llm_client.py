"""Client LLM unifié : point d'entrée unique utilisé par tous les agents pour
appeler un LLM, quel que soit le provider actif (Router LiteLLM en-dessous).

Nommage : le Prompt 3.1 demande une classe `LIDIALLMClient`. Le produit a été
renommé LIDIA -> NEXUS AI plus tôt dans le projet (voir mémoire de session) ;
cette classe s'appelle donc `NexusLLMClient` pour rester cohérent avec le
reste du code déjà renommé (nexus_network, conteneurs nexus_*, etc.).
"""

import uuid
from collections.abc import AsyncGenerator
from typing import TypeVar

import instructor
import litellm
import structlog
from pydantic import BaseModel

from backend.llm.gateway.cost_tracker import CostTracker
from backend.llm.gateway.litellm_config import build_router, resolve_primary_model_name

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# task_type (utilisé par les agents, cf. hybrid_router.py au Prompt 3.2) ->
# alias de modèle exposé par chaque provider dans litellm_config.py.
_TASK_TYPE_TO_ALIAS: dict[str, str] = {
    "classification": "fast",
    "seo_analysis": "fast",
    "sea_analysis": "fast",  # cohérent avec hybrid_router.TASK_TYPE_TO_LOCAL_MODEL (Prompt 5.2)
    "orchestration": "default",
    "content_generation": "default",
    "analytics": "default",
    "reporting": "default",
    "creative": "default",  # cohérent avec hybrid_router.TASK_TYPE_TO_LOCAL_MODEL (Prompt 5.7)
}
_DEFAULT_ALIAS = "default"


def _provider_from_model_name(model_name: str) -> str:
    """Dérive le provider d'un model_name Router (convention "provider-alias",
    voir litellm_config._build_deployment)."""
    return model_name.rsplit("-", 1)[0]


class NexusLLMClient:
    """Client LLM unifié, wrappant le Router LiteLLM (fallback, budget,
    retry  voir litellm_config.py). Singleton paresseux au niveau classe :
    le Router ne peut être construit que depuis une boucle asyncio active
    (voir build_router), jamais à l'import du module.
    """

    _router: litellm.Router | None = None

    def __init__(self, cost_tracker: CostTracker | None = None) -> None:
        self._cost_tracker = cost_tracker or CostTracker()

    async def _get_router(self) -> litellm.Router:
        if NexusLLMClient._router is None:
            NexusLLMClient._router = build_router()
        return NexusLLMClient._router

    def _resolve_model(self, model: str | None, task_type: str | None) -> str:
        """Résout le model_name Router à appeler : `model` explicite en
        priorité (déjà un alias Router, ex. "groq-default"), sinon dérivé de
        `task_type` via _TASK_TYPE_TO_ALIAS, sinon l'alias "default" du
        provider en tête de la chaîne de fallback active."""
        if model:
            return model
        alias = _TASK_TYPE_TO_ALIAS.get(task_type or "", _DEFAULT_ALIAS)
        return resolve_primary_model_name(alias)

    def _build_metadata(
        self, trace_id: str | None, session_id: str | None, user_id: str | None
    ) -> dict:
        """Métadonnées reconnues par l'intégration LangFuse native de LiteLLM
        (litellm_config.configure_langfuse_callbacks) : injectées dans chaque
        appel pour que chaque génération soit rattachée à son trace/session/
        utilisateur côté LangFuse."""
        return {
            "trace_id": trace_id or str(uuid.uuid4()),
            "session_id": session_id,
            "trace_user_id": user_id,
        }

    async def _track_cost(self, model_name: str, response, agent_name: str | None) -> None:
        try:
            cost = litellm.completion_cost(completion_response=response)
            usage = getattr(response, "usage", None)
            await self._cost_tracker.track_usage(
                provider=_provider_from_model_name(model_name),
                model=getattr(response, "model", model_name),
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                cost=cost or 0.0,
                agent_name=agent_name,
            )
        except Exception as exc:  # le tracking de coût ne doit jamais faire échouer l'appel LLM lui-même
            logger.warning("llm_client.cost_tracking_failed", model=model_name, error=str(exc))

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        task_type: str | None = None,
        client_id: str | None = None,
        agent_name: str | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """Complétion simple : retourne le texte de la réponse. Le fallback
        (Groq -> Together AI -> Fireworks AI -> moteur local) est géré par le
        Router lui-même  aucune boucle de retry manuelle ici."""
        router = await self._get_router()
        model_name = self._resolve_model(model, task_type)

        response = await router.acompletion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            metadata=self._build_metadata(trace_id, session_id, user_id),
        )
        await self._track_cost(model_name, response, agent_name)
        return response.choices[0].message.content or ""

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        task_type: str | None = None,
        client_id: str | None = None,
        agent_name: str | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Complétion en streaming : yield chaque delta de texte au fil de
        l'arrivée. Le coût n'est calculable qu'une fois le stream épuisé
        (litellm agrège l'usage sur le dernier chunk)  tracké après le
        dernier yield, pas pendant."""
        router = await self._get_router()
        model_name = self._resolve_model(model, task_type)

        response_stream = await router.acompletion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            metadata=self._build_metadata(trace_id, session_id, user_id),
            stream=True,
        )

        collected_response = None
        async for chunk in response_stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
            collected_response = chunk

        if collected_response is not None:
            await self._track_cost(model_name, collected_response, agent_name)

    async def complete_structured(
        self,
        prompt: str,
        response_model: type[T],
        model: str | None = None,
        task_type: str | None = None,
        client_id: str | None = None,
        agent_name: str | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> T:
        """Complétion structurée : retourne une instance validée de
        `response_model` (via instructor  function calling + validation +
        retry automatique en cas de sortie invalide)."""
        router = await self._get_router()
        model_name = self._resolve_model(model, task_type)

        instructor_client = instructor.from_litellm(router.acompletion, async_client=True)
        result, raw_response = await instructor_client.chat.completions.create_with_completion(
            model=model_name,
            response_model=response_model,
            messages=[{"role": "user", "content": prompt}],
            metadata=self._build_metadata(trace_id, session_id, user_id),
        )
        await self._track_cost(model_name, raw_response, agent_name)
        return result
