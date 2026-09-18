"""Configuration du provider Fireworks AI (deuxième fallback API  voir
settings.API_FALLBACK_PROVIDER  troisième option de failover dans la chaîne
Groq → Together AI → Fireworks AI → vLLM local, cf. stack_technique.md).

Point de vigilance documenté dans stack_technique.md : ne jamais architecturer
de dépendance exclusive à Groq (rachat de sa techno LPU par Nvidia fin 2025) 
Fireworks est le filet de sécurité si Together AI est également indisponible.
"""

from backend.config.settings import settings

MODELS = {
    "default": "fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct",
    "fast": "fireworks_ai/accounts/fireworks/models/llama-v3p1-8b-instruct",
}

RPM_LIMIT = 60
TPM_LIMIT = 60000


def get_provider_config() -> dict:
    """Retourne la configuration Fireworks AI, compatible avec les entrées
    `model_list` du Router LiteLLM."""
    return {
        "provider": "fireworks_ai",
        "models": MODELS,
        "api_key": settings.FIREWORKS_API_KEY,
        "api_base": None,
        "timeout": 30,
        "max_retries": 2,
        "rpm": RPM_LIMIT,
        "tpm": TPM_LIMIT,
    }
