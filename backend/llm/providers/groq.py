"""Configuration du provider Groq (API primaire par défaut  voir
settings.API_PRIMARY_PROVIDER  ultra rapide, ~500+ tok/s, cf. stack_technique.md).

Groq expose une API compatible OpenAI ; LiteLLM route dessus via le préfixe
de modèle "groq/<model>".
"""

from backend.config.settings import settings

# Modèles réellement hébergés par Groq (à revalider périodiquement  le
# catalogue Groq évolue plus vite que celui des fournisseurs "classiques").
MODELS = {
    "default": "groq/llama-3.3-70b-versatile",
    "fast": "groq/llama-3.1-8b-instant",
}

# Limites du tier gratuit Groq (ordre de grandeur, à ajuster selon le plan
# souscrit)  utilisées pour configurer le rate limiting côté LiteLLM Router.
RPM_LIMIT = 30
TPM_LIMIT = 6000


def get_provider_config() -> dict:
    """Retourne la configuration Groq, compatible avec les entrées `model_list`
    du Router LiteLLM (voir backend/llm/gateway/litellm_config.py)."""
    return {
        "provider": "groq",
        "models": MODELS,
        "api_key": settings.GROQ_API_KEY,
        "api_base": None,  # géré nativement par le préfixe "groq/" de LiteLLM
        "timeout": 20,
        "max_retries": 2,
        "rpm": RPM_LIMIT,
        "tpm": TPM_LIMIT,
    }
