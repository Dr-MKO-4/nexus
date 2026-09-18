"""Sélection dynamique du modèle/fournisseur LLM optimal selon le coût, la latence et la tâche."""

from backend.llm.router.hybrid_router import HybridRouter, RoutingDecision
from backend.llm.router.sensitivity_detector import is_sensitive

__all__ = [
    "HybridRouter",
    "RoutingDecision",
    "is_sensitive",
]
