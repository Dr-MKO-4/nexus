"""Point d'entrée unifié pour les appels LLM, gestion du cache, des quotas et de la résilience."""

from backend.llm.gateway.cost_tracker import CostTracker
from backend.llm.gateway.litellm_config import build_router, resolve_primary_model_name
from backend.llm.gateway.llm_client import NexusLLMClient
from backend.llm.gateway.prompt_loader import compile_template, get_prompt
from backend.llm.gateway.structured_output import parse_llm_json

__all__ = [
    "NexusLLMClient",
    "CostTracker",
    "build_router",
    "resolve_primary_model_name",
    "get_prompt",
    "compile_template",
    "parse_llm_json",
]
