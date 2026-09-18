"""Configuration du serveur vLLM local (LLM_MODE=local ou hybrid, moteur de
production  voir stack_technique.md : vLLM soutient la charge concurrente là
où Ollama dégrade, latence P99 80ms vs 673ms sous charge).

vLLM expose une API compatible OpenAI ; LiteLLM route via le préfixe
"hosted_vllm/<model>" avec `api_base` pointant vers le serveur local.
"""

from backend.config.settings import settings

MODELS = {
    "default": settings.LOCAL_DEFAULT_MODEL,
    "fast": settings.LOCAL_FAST_MODEL,
}


def get_provider_config() -> dict:
    """Retourne la configuration vLLM locale, compatible avec les entrées
    `model_list` du Router LiteLLM. Pas de clé API : serveur auto-hébergé."""
    return {
        "provider": "vllm",
        "models": {
            alias: f"hosted_vllm/{model_name}" for alias, model_name in MODELS.items()
        },
        "api_key": None,
        "api_base": settings.VLLM_BASE_URL,
        "timeout": 60,  # inférence locale : pas de tarif au token, mais latence plus variable
        "max_retries": 1,  # pas de sens de retenter agressivement un serveur local en difficulté
        "rpm": None,  # pas de rate limit fournisseur : la charge réelle est la charge GPU
    }
