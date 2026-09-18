"""Configuration du provider Together AI (fallback API par défaut  voir
settings.API_FALLBACK_PROVIDER  plus large catalogue de modèles open source,
cf. stack_technique.md).
"""

from backend.config.settings import settings

# Together AI héberge Qwen3.5, seul modèle open source avec un support natif
# du français en qualité production (voir stack_technique.md)  d'où son rôle
# de fallback : il couvre aussi bien les tâches Llama que le contenu français.
MODELS = {
    "default": "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "multilingual": "together_ai/Qwen/Qwen2.5-72B-Instruct-Turbo",
    "fast": "together_ai/meta-llama/Llama-3.2-3B-Instruct-Turbo",
}

RPM_LIMIT = 60
TPM_LIMIT = 60000


def get_provider_config() -> dict:
    """Retourne la configuration Together AI, compatible avec les entrées
    `model_list` du Router LiteLLM."""
    return {
        "provider": "together_ai",
        "models": MODELS,
        "api_key": settings.TOGETHER_API_KEY,
        "api_base": None,
        "timeout": 30,
        "max_retries": 2,
        "rpm": RPM_LIMIT,
        "tpm": TPM_LIMIT,
    }
