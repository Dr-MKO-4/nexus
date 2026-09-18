"""Routeur LLM hybride : décide provider/modèle/coût estimé pour chaque
tâche, dans l'ordre de priorité imposé (Prompt 3.2) : sensibilité des
données > charge GPU locale > budget journalier > complexité de la tâche >
LLM_MODE actif.

Ce module ne fait PAS l'appel LLM lui-même (c'est le rôle de
backend.llm.gateway.llm_client.NexusLLMClient, Prompt 3.1) : il ne fait que
décider, sous forme de `RoutingDecision`, structure de données que
l'appelant traduit ensuite en appel réel.
"""

from collections.abc import Callable

import structlog
from pydantic import BaseModel

from backend.config.settings import settings
from backend.llm.gateway.cost_tracker import CostTracker
from backend.llm.router.sensitivity_detector import is_sensitive
from backend.pytorch_models.classifiers.complexity_classifier import (
    ComplexityClassifier,
    ComplexityLabel,
)

logger = structlog.get_logger(__name__)

# Table task_type -> modèle local (Prompt 3.2), utilisée en priorité quand la
# décision route vers l'inférence locale : un task_type explicitement listé
# est un signal plus fort que la classification de complexité générique.
TASK_TYPE_TO_LOCAL_MODEL: dict[str, str] = {
    "orchestration": "llama3.3:70b",
    "content_generation": "qwen3.5:72b",
    "classification": "mistral:7b",
    "seo_analysis": "mistral:7b",
    # Extension au-delà de la table littérale du Prompt 3.2 (6 entrées) :
    # l'Agent SEA (Prompt 5.2) exige explicitement Mistral 7B mais n'a pas
    # d'entrée dédiée  "sea_analysis" suit le même mapping que
    # "seo_analysis" plutôt que de réutiliser "classification" (sémantique
    # différente) pour cet agent.
    "sea_analysis": "mistral:7b",
    "analytics": "llama3.3:70b",
    "reporting": "qwen3.5:72b",
    # Extension au-delà de la table littérale du Prompt 3.2 : l'Agent
    # Creative (Prompt 5.7) construit des prompts de génération d'image
    # (VISUAL_GENERATION_PROMPT) et parse des briefs  même exigence de
    # qualité/nuance que "content_generation", donc même modèle.
    "creative": "qwen3.5:72b",
}

# Modèle local par défaut pour un task_type absent de la table ci-dessus,
# selon la complexité détectée (PyTorch, ou heuristique de fallback tant que
# le classifieur n'est pas entraîné).
_COMPLEXITY_TO_LOCAL_MODEL: dict[ComplexityLabel, str] = {
    "simple": "mistral:7b",
    "medium": "llama3.3:70b",
    "complex": "qwen3.5:72b",
}

# Alias Router LiteLLM correspondant (voir litellm_config.build_model_list,
# llm_client._TASK_TYPE_TO_ALIAS) : "fast" pour les tâches légères, "default"
# pour le reste. Qwen3.5 n'a pas d'équivalent API direct dans le model_list
# actuel (aucun provider API ne l'expose sous cet alias) - "default" reste le
# choix le plus proche disponible.
_MODEL_TO_API_ALIAS: dict[str, str] = {
    "mistral:7b": "fast",
    "llama3.3:70b": "default",
    "qwen3.5:72b": "default",
}

# Ordre de fallback API imposé (cohérent avec litellm_config._API_FALLBACK_ORDER)
_API_FALLBACK_CHAIN = ("groq", "together_ai", "fireworks_ai")

# Coût estimé en ordre de grandeur seulement (reasoning affiché avant l'appel
# réel)  le coût facturé après coup fait foi via litellm.completion_cost,
# voir cost_tracker.py. ~1500 tokens = taille moyenne d'une tâche agent.
_ESTIMATED_TASK_TOKENS = 1.5
_ESTIMATED_COST_PER_1K_TOKENS_API = 0.001
_ESTIMATED_COST_LOCAL = 0.0


class RoutingDecision(BaseModel):
    provider: str
    model: str
    reasoning: str
    estimated_cost: float
    fallback_chain: list[str]


def _default_gpu_load() -> float:
    """Lit la charge GPU locale (métrique Prometheus, ex. DCGM exporter).

    Non câblé à ce stade : `infrastructure/prometheus/prometheus.yml` ne
    scrape aujourd'hui que langgraph_api/pytorch_models/flower/cadvisor/
    node_exporter  aucun exporter GPU n'est encore déployé dans
    docker-compose.yml. Retourne 0.0 (aucune contrainte GPU perçue) jusqu'à
    l'ajout de cette intégration ; injecter `gpu_load_provider` dans
    `HybridRouter.__init__` pour tester ou brancher une vraie source
    entre-temps.
    """
    return 0.0


class HybridRouter:
    def __init__(
        self,
        classifier: ComplexityClassifier | None = None,
        cost_tracker: CostTracker | None = None,
        gpu_load_provider: Callable[[], float] | None = None,
    ) -> None:
        self._classifier = classifier or ComplexityClassifier.from_checkpoint()
        self._cost_tracker = cost_tracker or CostTracker()
        self._gpu_load_provider = gpu_load_provider or _default_gpu_load

    async def route(self, task: dict) -> RoutingDecision:
        """`task` : {"description": str, "task_type": str | None}."""
        description = task.get("description", "")
        task_type = task.get("task_type")

        # 1. Sensibilité des données -> force local, prioritaire sur tout le reste.
        if is_sensitive(description, task_type):
            return self._route_local(task_type, description, reasoning_prefix="Données sensibles détectées")

        # 2. Charge GPU locale -> déborder sur API si au-delà du seuil.
        gpu_load = self._gpu_load_provider()
        if gpu_load > settings.HYBRID_GPU_LOAD_THRESHOLD:
            return await self._route_api(
                task_type,
                description,
                reasoning_prefix=(
                    f"Charge GPU locale {gpu_load:.0%} > seuil "
                    f"{settings.HYBRID_GPU_LOAD_THRESHOLD:.0%}"
                ),
            )

        # 3. Budget journalier -> basculer local si dépassé (l'inférence
        # locale n'a pas de coût marginal au token).
        if await self._cost_tracker.check_budget_exceeded():
            return self._route_local(
                task_type,
                description,
                reasoning_prefix=f"Budget journalier ({settings.HYBRID_COST_DAILY_LIMIT_USD}$) dépassé",
            )

        # 4 + 5. Complexité de la tâche (calculée dans _route_local/_route_api
        # pour figurer dans le reasoning) puis application du LLM_MODE actif.
        if settings.LLM_MODE == "local":
            return self._route_local(task_type, description, reasoning_prefix="LLM_MODE=local")
        if settings.LLM_MODE == "api":
            return await self._route_api(task_type, description, reasoning_prefix="LLM_MODE=api")

        # hybrid, aucune contrainte ci-dessus déclenchée : l'API (latence
        # prévisible, pas de contention GPU locale) est le choix par défaut.
        return await self._route_api(
            task_type, description, reasoning_prefix="LLM_MODE=hybrid, aucune contrainte déclenchée"
        )

    def _resolve_model(self, task_type: str | None, description: str) -> tuple[str, ComplexityLabel]:
        complexity = self._classifier.predict(description)
        if task_type in TASK_TYPE_TO_LOCAL_MODEL:
            return TASK_TYPE_TO_LOCAL_MODEL[task_type], complexity
        return _COMPLEXITY_TO_LOCAL_MODEL[complexity], complexity

    def _route_local(self, task_type: str | None, description: str, *, reasoning_prefix: str) -> RoutingDecision:
        model, complexity = self._resolve_model(task_type, description)
        provider = settings.LOCAL_INFERENCE_ENGINE
        reasoning = f"{reasoning_prefix} -> inférence locale ({provider}), complexité={complexity}, modèle={model}"
        logger.info("hybrid_router.decision", provider=provider, model=model, reasoning=reasoning)
        return RoutingDecision(
            provider=provider,
            model=model,
            reasoning=reasoning,
            estimated_cost=_ESTIMATED_COST_LOCAL,
            fallback_chain=[provider],
        )

    async def _route_api(self, task_type: str | None, description: str, *, reasoning_prefix: str) -> RoutingDecision:
        local_model, complexity = self._resolve_model(task_type, description)
        alias = _MODEL_TO_API_ALIAS.get(local_model, "default")
        provider = _API_FALLBACK_CHAIN[0]  # toujours Groq en tête, voir litellm_config.py
        fallback_chain = [*_API_FALLBACK_CHAIN, settings.LOCAL_INFERENCE_ENGINE]
        estimated_cost = _ESTIMATED_COST_PER_1K_TOKENS_API * _ESTIMATED_TASK_TOKENS
        reasoning = f"{reasoning_prefix} -> API ({provider}), complexité={complexity}, alias={alias}"
        logger.info(
            "hybrid_router.decision", provider=provider, model=f"{provider}-{alias}", reasoning=reasoning
        )
        return RoutingDecision(
            provider=provider,
            model=f"{provider}-{alias}",
            reasoning=reasoning,
            estimated_cost=estimated_cost,
            fallback_chain=fallback_chain,
        )
