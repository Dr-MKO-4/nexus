"""Configuration du provider Mistral API (l'un des trois choix possibles pour
settings.API_PRIMARY_PROVIDER). API native Mistral (pas un modèle hébergé par
un tiers)  LiteLLM route via le préfixe "mistral/<model>".
"""

from backend.config.settings import settings

MODELS = {
    "default": "mistral/mistral-large-latest",
    "fast": "mistral/open-mistral-7b",
}

RPM_LIMIT = 30
TPM_LIMIT = 30000


def get_provider_config() -> dict:
    """Retourne la configuration Mistral API, compatible avec les entrées
    `model_list` du Router LiteLLM."""
    return {
        "provider": "mistral",
        "models": MODELS,
        "api_key": settings.MISTRAL_API_KEY,
        "api_base": None,
        "timeout": 30,
        "max_retries": 2,
        "rpm": RPM_LIMIT,
        "tpm": TPM_LIMIT,
    }
