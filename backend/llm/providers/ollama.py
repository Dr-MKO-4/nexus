"""Configuration du serveur Ollama local (LLM_MODE=local, développement
uniquement  voir stack_technique.md : Ollama pour le développement local des
agents, vLLM dès que le système passe en production avec plusieurs agents en
parallèle).

LiteLLM route via le préfixe "ollama_chat/<model>" (format chat, recommandé
par LiteLLM pour les modèles instruct) avec `api_base` pointant vers le
serveur local.
"""

from backend.config.settings import settings

MODELS = {
    "default": settings.LOCAL_DEFAULT_MODEL,
    "fast": settings.LOCAL_FAST_MODEL,
}


def get_provider_config() -> dict:
    """Retourne la configuration Ollama locale, compatible avec les entrées
    `model_list` du Router LiteLLM. Pas de clé API : serveur auto-hébergé."""
    return {
        "provider": "ollama",
        "models": {
            alias: f"ollama_chat/{model_name}" for alias, model_name in MODELS.items()
        },
        "api_key": None,
        "api_base": settings.OLLAMA_BASE_URL,
        "timeout": 60,
        "max_retries": 1,
        "rpm": None,
    }
