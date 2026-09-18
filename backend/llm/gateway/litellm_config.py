"""Configuration LiteLLM centrale : model_list du Router, ordre de fallback,
retry/timeout par provider, budget journalier, callbacks LangFuse.

Le type attendu par `Router.__init__(provider_budget_config=...)` a bougé
d'une version de litellm à l'autre, constaté en pratique dans CE sandbox
(pas une supposition) : litellm==1.55.0 (le plancher imposé par
`requirements/base.txt`, réellement installé au moment de ce correctif)
expose `ProviderBudgetInfo` dans `litellm.types.router` avec les champs
`time_period`/`budget_limit` ; des versions plus récentes (1.101.0,
installée à un autre moment de ce projet) l'ont renommé en `BudgetConfig`
dans `litellm.types.utils`, avec les mêmes champs. Import tolérant aux deux
plutôt qu'un pin de version supplémentaire  évite de recasser cet import
au prochain changement de version dans un sens ou l'autre.
"""

from __future__ import annotations

import litellm
import structlog
from litellm import Router

try:
    from litellm.types.utils import BudgetConfig
except ImportError:
    from litellm.types.router import ProviderBudgetInfo as BudgetConfig

from backend.config.settings import settings
from backend.llm.providers import fireworks, groq, mistral, ollama, together, vllm

logger = structlog.get_logger(__name__)

# Ordre de fallback imposé (Prompt 3.1) pour les providers API : Groq d'abord
# (ultra rapide), puis Together AI, puis Fireworks AI. Le moteur local
# (vLLM ou Ollama selon settings.LOCAL_INFERENCE_ENGINE) ferme la chaîne.
_API_FALLBACK_ORDER = ("groq", "together_ai", "fireworks_ai")


def _collect_provider_configs() -> dict[str, dict]:
    """Rassemble les configs des providers pertinents pour le LLM_MODE actif.

    - local  : uniquement le moteur local (LOCAL_INFERENCE_ENGINE).
    - api    : les providers API (Groq, Together, Fireworks, + Mistral si
               explicitement configuré comme provider primaire).
    - hybrid : les deux simultanément  c'est ce qui rend le fallback complet
               (API -> local) possible.
    """
    configs: dict[str, dict] = {}

    if settings.LLM_MODE in ("local", "hybrid"):
        local_module = vllm if settings.LOCAL_INFERENCE_ENGINE == "vllm" else ollama
        configs[settings.LOCAL_INFERENCE_ENGINE] = local_module.get_provider_config()

    if settings.LLM_MODE in ("api", "hybrid"):
        api_candidates = {
            "groq": groq.get_provider_config(),
            "together_ai": together.get_provider_config(),
            "fireworks_ai": fireworks.get_provider_config(),
        }
        # Mistral n'est ajouté que s'il est explicitement le provider primaire :
        # il n'appartient pas à la chaîne de fallback imposée par le Prompt 3.1
        # (Groq -> Together -> Fireworks -> vLLM), qui ne le mentionne pas.
        if settings.API_PRIMARY_PROVIDER == "mistral":
            api_candidates["mistral"] = mistral.get_provider_config()

        for provider_key, provider_config in api_candidates.items():
            # Une clé API vide/absente casserait la construction du Router
            # (litellm tente d'initialiser un client OpenAI-SDK sans
            # credentials et lève une erreur non récupérable) - on exclut
            # proprement le provider plutôt que de faire planter tout le
            # gateway. Cas réel en dev : .env.development laisse les clés
            # API vides ("") par défaut en LLM_MODE=local.
            if not provider_config.get("api_key"):
                logger.warning("litellm_config.provider_skipped_no_api_key", provider=provider_key)
                continue
            configs[provider_key] = provider_config

    return configs


def _build_deployment(provider_key: str, alias: str, provider_config: dict) -> dict:
    """Construit une entrée `model_list` (format Router LiteLLM) pour un alias
    donné ("default"/"fast") d'un provider. `model_name` est préfixé par le
    provider (ex. "groq-default") pour que chaque provider ait une entrée
    distincte, condition nécessaire au fallback ordonné (voir build_fallbacks) :
    des déploiements partageant le même model_name forment un pool équilibré
    en charge, pas une chaîne de secours ordonnée.
    """
    litellm_params: dict = {
        "model": provider_config["models"][alias],
        "timeout": provider_config["timeout"],
        "max_retries": provider_config["max_retries"],
    }
    if provider_config.get("api_key"):
        litellm_params["api_key"] = provider_config["api_key"]
    if provider_config.get("api_base"):
        litellm_params["api_base"] = provider_config["api_base"]
    if provider_config.get("rpm"):
        litellm_params["rpm"] = provider_config["rpm"]
    if provider_config.get("tpm"):
        litellm_params["tpm"] = provider_config["tpm"]

    return {
        "model_name": f"{provider_key}-{alias}",
        "litellm_params": litellm_params,
        "model_info": {"provider": provider_key},
    }


def build_model_list(provider_configs: dict[str, dict]) -> list[dict]:
    return [
        _build_deployment(provider_key, alias, config)
        for provider_key, config in provider_configs.items()
        for alias in config["models"]
    ]


def _build_provider_chain(provider_configs: dict[str, dict]) -> list[str]:
    """Ordre Groq -> Together AI -> Fireworks AI -> moteur local, restreint
    aux providers réellement présents dans `provider_configs` (cohérent avec
    le LLM_MODE actif). Partagé par build_fallbacks() et
    resolve_primary_model_name()."""
    chain = [p for p in _API_FALLBACK_ORDER if p in provider_configs]
    if settings.LOCAL_INFERENCE_ENGINE in provider_configs:
        chain.append(settings.LOCAL_INFERENCE_ENGINE)
    return chain


def build_fallbacks(provider_configs: dict[str, dict]) -> list[dict[str, list[str]]]:
    """Construit la chaîne de fallback ordonnée pour chaque alias ("default",
    "fast") à partir des seuls providers réellement présents dans
    `provider_configs` (donc cohérent avec le LLM_MODE actif : en mode "api"
    pur, la chaîne s'arrête à Fireworks ; en mode "local" pur, il n'y a rien
    à basculer ; en mode "hybrid", la chaîne va jusqu'au moteur local).
    """
    chain = _build_provider_chain(provider_configs)

    fallbacks: list[dict[str, list[str]]] = []
    for alias in ("default", "fast"):
        ordered_names = [f"{p}-{alias}" for p in chain if alias in provider_configs[p]["models"]]
        if len(ordered_names) > 1:
            fallbacks.append({ordered_names[0]: ordered_names[1:]})
    return fallbacks


def resolve_primary_model_name(alias: str = "default") -> str:
    """Retourne le model_name Router (ex. "groq-default") en tête de la chaîne
    de fallback pour l'alias donné, compte tenu du LLM_MODE actif et des clés
    API réellement configurées. Utilisé par llm_client.py pour choisir un
    modèle par défaut quand l'appelant ne précise pas de `model` explicite.
    """
    provider_configs = _collect_provider_configs()
    chain = _build_provider_chain(provider_configs)
    for provider_key in chain:
        if alias in provider_configs[provider_key]["models"]:
            return f"{provider_key}-{alias}"
    raise RuntimeError(
        f"Aucun provider actif n'expose l'alias {alias!r} (LLM_MODE={settings.LLM_MODE!r})."
    )


def build_provider_budget_config(provider_configs: dict[str, dict]) -> dict[str, BudgetConfig]:
    """Budget journalier par provider (Router.provider_budget_config).

    settings.py n'expose qu'un budget global (HYBRID_COST_DAILY_LIMIT_USD),
    pas un budget par provider  appliqué ici identiquement à chaque provider
    API. Absent pour les moteurs locaux (vLLM/Ollama) : pas de coût au token.
    """
    return {
        provider_key: BudgetConfig(
            time_period="1d", budget_limit=settings.HYBRID_COST_DAILY_LIMIT_USD
        )
        for provider_key in provider_configs
        if provider_key not in ("vllm", "ollama")
    }


_LANGFUSE_CALLBACK_CHECKED = False
_LANGFUSE_CALLBACK_USABLE = False


def _apply_langfuse_version_shim() -> None:
    """langfuse>=3.0 (notre exigence, Prompt 1.4) a supprimé le sous-module
    `langfuse.version` (renommé `langfuse._version`), utilisé par le code de
    détection de version de l'intégration LiteLLM<->LangFuse "legacy".
    Injecte un module de compatibilité minimal plutôt que de dépendre d'un
    changement côté LiteLLM ou LangFuse."""
    import sys
    import types

    import langfuse

    if hasattr(langfuse, "version"):
        return
    shim = types.ModuleType("langfuse.version")
    shim.__version__ = langfuse.__version__
    sys.modules["langfuse.version"] = shim
    langfuse.version = shim


def _langfuse_callback_is_usable() -> bool:
    """Vérifie une fois (résultat mis en cache) que l'intégration "langfuse"
    native de LiteLLM peut réellement s'initialiser avec la version de
    langfuse installée, avant de l'activer pour de vrai.

    Bug constaté empiriquement (litellm 1.55.0 à 1.65.0 x langfuse 4.15.2,
    donc pas propre à une version précise) : au-delà du sous-module
    `langfuse.version` manquant (corrigé par le shim ci-dessus),
    l'intégration instancie `Langfuse(..., sdk_integration=...)`  paramètre
    supprimé du constructeur dans le SDK v3/v4. Plutôt que de supposer que
    cela fonctionne (le Prompt 3.1 demandait juste "callbacks LangFuse"),
    cette fonction PROUVE que l'intégration s'initialise avant de l'activer,
    et désactive proprement (log + pas de callback) si ce n'est pas le cas 
    pour ne jamais faire planter un appel LLM réel à cause du tracing.
    """
    global _LANGFUSE_CALLBACK_CHECKED, _LANGFUSE_CALLBACK_USABLE
    if _LANGFUSE_CALLBACK_CHECKED:
        return _LANGFUSE_CALLBACK_USABLE

    _LANGFUSE_CALLBACK_CHECKED = True
    try:
        _apply_langfuse_version_shim()
        from litellm.integrations.langfuse.langfuse import LangFuseLogger

        LangFuseLogger(
            langfuse_public_key=settings.LANGFUSE_PUBLIC_KEY,
            langfuse_secret=settings.LANGFUSE_SECRET_KEY,
            langfuse_host=settings.LANGFUSE_HOST,
        )
        _LANGFUSE_CALLBACK_USABLE = True
    except Exception as exc:
        logger.warning("litellm_config.langfuse_integration_incompatible", error=str(exc))
        _LANGFUSE_CALLBACK_USABLE = False

    return _LANGFUSE_CALLBACK_USABLE


def configure_langfuse_callbacks() -> None:
    """Active le tracing LangFuse automatique pour tous les appels LiteLLM 
    seulement si l'intégration s'avère réellement utilisable avec la version
    de langfuse installée (voir _langfuse_callback_is_usable) ; sinon,
    n'active rien plutôt que de faire planter chaque appel LLM.

    Repose sur LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY/LANGFUSE_HOST présents
    dans l'environnement du PROCESS (os.environ)  LiteLLM les lit directement
    depuis l'OS, pas depuis notre objet Settings Pydantic. `env_file: .env`
    dans docker-compose.yml les injecte bien dans l'environnement du
    conteneur, donc cohérent en déploiement Docker ; en exécution locale hors
    Docker, s'assurer que le `.env` est chargé dans le shell (pas seulement
    lu par pydantic-settings) avant de démarrer le process.
    """
    if _langfuse_callback_is_usable():
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
    else:
        litellm.success_callback = []
        litellm.failure_callback = []


def build_router() -> Router:
    """Construit le Router LiteLLM complet : model_list, fallbacks ordonnés,
    budget journalier par provider, callbacks LangFuse. Point d'entrée unique
    consommé par llm_client.py.

    IMPORTANT : doit être appelée depuis une boucle asyncio déjà active (à
    l'intérieur d'une coroutine, ex. le lifespan FastAPI au démarrage), jamais
    au niveau module ni depuis du code synchrone pur. `provider_budget_config`
    fait démarrer en interne une tâche de fond asyncio dès la construction du
    Router (`ProviderBudgetLimiting.__init__` -> `asyncio.create_task(...)`)
    - sans boucle active, cela lève `RuntimeError: no running event loop`
    (vérifié empiriquement). `llm_client.py` respecte cette contrainte en ne
    construisant le Router qu'au premier appel async (singleton paresseux).
    """
    provider_configs = _collect_provider_configs()
    if not provider_configs:
        raise RuntimeError(
            f"Aucun provider LLM disponible pour LLM_MODE={settings.LLM_MODE!r} - "
            "vérifier la configuration (settings.LLM_MODE, LOCAL_INFERENCE_ENGINE, "
            "API_PRIMARY_PROVIDER)."
        )

    configure_langfuse_callbacks()

    router = Router(
        model_list=build_model_list(provider_configs),
        fallbacks=build_fallbacks(provider_configs),
        provider_budget_config=build_provider_budget_config(provider_configs) or None,
        redis_url=str(settings.REDIS_URL),
        num_retries=2,
        timeout=60,
    )
    logger.info(
        "litellm_router.built",
        mode=settings.LLM_MODE,
        providers=sorted(provider_configs),
    )
    return router
