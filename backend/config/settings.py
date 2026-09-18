"""Configuration applicative centralisée, chargée depuis les variables d'environnement.

Toutes les valeurs sont validées strictement par Pydantic au démarrage de
l'application : une variable manquante ou mal typée fait échouer le
lancement immédiatement plutôt qu'en cours d'exécution.
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # LLM  mode de fonctionnement et modèles locaux
    # ------------------------------------------------------------------

    LLM_MODE: Literal["local", "api", "hybrid"] = Field(
        default="hybrid",
        description="Stratégie d'inférence : modèles locaux uniquement, API uniquement, ou mix des deux.",
    )
    LOCAL_INFERENCE_ENGINE: Literal["ollama", "vllm"] = Field(
        default="ollama",
        description="Moteur d'inférence utilisé pour les modèles hébergés localement.",
    )
    LOCAL_DEFAULT_MODEL: str = Field(
        default="llama3.3:70b",
        description="Modèle local utilisé par défaut pour les tâches génériques.",
    )
    LOCAL_FAST_MODEL: str = Field(
        default="mistral:7b",
        description="Modèle local léger utilisé pour les tâches nécessitant une faible latence.",
    )
    VLLM_BASE_URL: str = Field(
        default="http://vllm:8000",
        description=(
            "URL du serveur vLLM local (API compatible OpenAI). Défaut : nom de "
            "service Docker Compose interne (voir docker-compose.yml, profil gpu). "
            "Absente de la spec initiale (Prompt 1.2)  ajoutée au Prompt 3.1 pour "
            "backend/llm/providers/vllm.py."
        ),
    )
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        description=(
            "URL du serveur Ollama local. Pas de service docker-compose dédié : "
            "Ollama tourne sur la machine hôte en développement (voir "
            "stack_technique.md  Ollama en dev, vLLM en production). Absente de "
            "la spec initiale (Prompt 1.2)  ajoutée au Prompt 3.1 pour "
            "backend/llm/providers/ollama.py."
        ),
    )

    # ------------------------------------------------------------------
    # LLM  fournisseurs API
    # ------------------------------------------------------------------

    API_PRIMARY_PROVIDER: Literal["groq", "together", "mistral"] = Field(
        default="groq",
        description="Fournisseur LLM API utilisé en priorité.",
    )
    API_FALLBACK_PROVIDER: Literal["together", "fireworks"] = Field(
        default="together",
        description="Fournisseur LLM API utilisé en repli si le fournisseur primaire échoue ou est indisponible.",
    )
    API_DEFAULT_MODEL: str = Field(
        description="Identifiant du modèle par défaut chez le fournisseur API primaire.",
    )
    API_FAST_MODEL: str = Field(
        description="Identifiant du modèle rapide/économique chez le fournisseur API primaire.",
    )

    # ------------------------------------------------------------------
    # LLM  arbitrage du mode hybride
    # ------------------------------------------------------------------

    HYBRID_COST_DAILY_LIMIT_USD: float = Field(
        default=50.0,
        ge=0,
        description="Plafond de dépense quotidienne (en USD) sur les appels API avant bascule forcée vers l'inférence locale.",
    )
    HYBRID_GPU_LOAD_THRESHOLD: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Charge GPU locale (0-1) au-delà de laquelle les requêtes sont routées vers l'API plutôt que le moteur local.",
    )
    HYBRID_SENSITIVE_TASKS: list[str] = Field(
        default_factory=list,
        description="Liste des types de tâches considérées sensibles, toujours exécutées en local en mode hybride (ex: données clients).",
    )

    # ------------------------------------------------------------------
    # Base de données & stockage
    # ------------------------------------------------------------------

    DATABASE_URL: PostgresDsn = Field(
        description="URL de connexion PostgreSQL (base relationnelle principale).",
    )
    REDIS_URL: RedisDsn = Field(
        description="URL de connexion Redis (cache, files d'attente Celery, état de session).",
    )
    QDRANT_HOST: str = Field(
        description="Hôte du serveur Qdrant (base vectorielle pour les embeddings).",
    )
    QDRANT_PORT: int = Field(
        default=6333,
        ge=1,
        le=65535,
        description="Port du serveur Qdrant.",
    )
    PYTORCH_MODELS_URL: str = Field(
        default="http://pytorch_models:8001",
        description=(
            "URL du service pytorch_models (classification, embeddings, scoring, "
            "anomalies). Défaut : nom de service Docker Compose interne au réseau "
            "nexus_network. Absente de la spec initiale (Prompt 1.2)  ajoutée au "
            "Prompt 2.3 quand embedding_manager.py est devenu un client HTTP vers "
            "ce service plutôt que de charger sentence-transformers/CLIP en local."
        ),
    )
    SEARXNG_BASE_URL: str = Field(
        default="http://searxng:8080",
        description=(
            "URL du service SearXNG (métamoteur de recherche self-hosted, repli "
            "gratuit pour la recherche de mots-clés et la veille SERP). Défaut : "
            "nom de service Docker Compose interne. Absente de la spec initiale "
            "(Prompt 1.2)  ajoutée au Prompt 5.1 pour tools/seo/keyword_research.py."
        ),
    )
    N8N_BASE_URL: str = Field(
        default="http://n8n:5678",
        description=(
            "URL de l'instance n8n (automatisation de la publication sociale). "
            "Défaut : nom de service Docker Compose interne. Absente de la spec "
            "initiale (Prompt 1.2)  ajoutée au Prompt 5.4 pour tools/social/n8n_client.py."
        ),
    )
    N8N_API_KEY: Optional[str] = Field(
        default=None,
        description="Clé API n8n (authentification des appels à l'API REST /api/v1/*, ex. get_workflow_status).",
    )
    MAUTIC_BASE_URL: str = Field(
        default="http://mautic:8080",
        description=(
            "URL de l'instance Mautic (marketing automation email). Défaut : "
            "nom de service Docker Compose interne. Absente de la spec initiale "
            "(Prompt 1.2)  ajoutée au Prompt 5.5 pour tools/email/mautic_client.py."
        ),
    )
    MAUTIC_CLIENT_ID: Optional[str] = Field(
        default=None, description="Client ID OAuth2 Mautic (grant_type=client_credentials)."
    )
    MAUTIC_CLIENT_SECRET: Optional[str] = Field(default=None, description="Client Secret OAuth2 Mautic.")
    MATOMO_BASE_URL: str = Field(
        default="http://matomo:8080",
        description=(
            "URL de l'instance Matomo (analytics web). Défaut : nom de service "
            "Docker Compose interne. Absente de la spec initiale (Prompt 1.2)  "
            "ajoutée au Prompt 5.6 pour tools/analytics/matomo_client.py."
        ),
    )
    MATOMO_API_TOKEN: Optional[str] = Field(default=None, description="Token d'authentification API Matomo (token_auth).")

    # ------------------------------------------------------------------
    # Observabilité  LangFuse
    # ------------------------------------------------------------------

    LANGFUSE_PUBLIC_KEY: str = Field(
        description="Clé publique LangFuse pour le tracing des agents et des appels LLM.",
    )
    LANGFUSE_SECRET_KEY: str = Field(
        description="Clé secrète LangFuse.",
    )
    LANGFUSE_HOST: str = Field(
        description="URL de l'instance LangFuse (cloud ou self-hosted).",
    )

    # ------------------------------------------------------------------
    # Fournisseurs LLM  clés API
    # ------------------------------------------------------------------

    GROQ_API_KEY: Optional[str] = Field(default=None, description="Clé API Groq.")
    TOGETHER_API_KEY: Optional[str] = Field(default=None, description="Clé API Together AI.")
    MISTRAL_API_KEY: Optional[str] = Field(default=None, description="Clé API Mistral.")
    FIREWORKS_API_KEY: Optional[str] = Field(default=None, description="Clé API Fireworks AI.")

    # ------------------------------------------------------------------
    # Intégrations marketing tierces
    # ------------------------------------------------------------------

    GOOGLE_ADS_DEVELOPER_TOKEN: Optional[str] = Field(
        default=None, description="Token développeur de l'API Google Ads.",
    )
    GOOGLE_ADS_CLIENT_ID: Optional[str] = Field(
        default=None, description="Client ID OAuth2 pour l'API Google Ads.",
    )
    GOOGLE_ADS_CLIENT_SECRET: Optional[str] = Field(
        default=None, description="Client secret OAuth2 pour l'API Google Ads.",
    )
    META_APP_ID: Optional[str] = Field(
        default=None, description="ID de l'application Meta (Facebook/Instagram Ads).",
    )
    META_APP_SECRET: Optional[str] = Field(
        default=None, description="Secret de l'application Meta.",
    )
    FIGMA_ACCESS_TOKEN: Optional[str] = Field(
        default=None, description="Token d'accès personnel Figma (agent créatif).",
    )
    COMFYUI_BASE_URL: str = Field(
        default="http://comfyui:8188",
        description=(
            "URL du service ComfyUI (génération d'images Flux/SDXL, upscale). "
            "Défaut : nom de service Docker Compose interne. Absente de la spec "
            "initiale (Prompt 1.2)  ajoutée au Prompt 5.7 pour "
            "tools/creative/comfyui_client.py."
        ),
    )
    COMFYUI_LORA_DIR: str = Field(
        default="/data/comfyui/models/loras",
        description=(
            "Répertoire `models/loras` de ComfyUI, monté en volume partagé "
            "avec le worker d'entraînement LoRA (tools/creative/lora_trainer.py: "
            "export_lora)  ComfyUI et le worker doivent voir le même chemin "
            "pour qu'un LoRA fraîchement entraîné soit utilisable sans "
            "redémarrage/upload manuel."
        ),
    )
    SERPER_API_KEY: Optional[str] = Field(
        default=None, description="Clé API Serper (recherche Google pour l'agent SEO).",
    )

    # ------------------------------------------------------------------
    # Sécurité & environnement
    # ------------------------------------------------------------------

    SECRET_KEY: str = Field(
        description="Clé secrète applicative utilisée pour la signature des tokens (JWT, sessions).",
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="Algorithme de signature JWT (HMAC avec SECRET_KEY, pas de paire de clés asymétrique à ce stade).",
    )
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="Durée de validité d'un access token JWT (backend/api/auth.py, Prompt 7.1).",
    )
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        description="Durée de validité d'un refresh token JWT (backend/api/auth.py, Prompt 7.1).",
    )
    DEBUG: bool = Field(
        default=False,
        description="Active le mode debug (logs verbeux, reload automatique, stack traces détaillées).",
    )
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Environnement d'exécution courant, utilisé pour adapter le comportement de l'application.",
    )
    CORS_ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Origines autorisées par le middleware CORS de backend/api/main.py (Prompt 7.1)  l'URL du frontend NEXUS AI en développement par défaut.",
    )

    # ------------------------------------------------------------------
    # Tâches asynchrones  Celery
    # ------------------------------------------------------------------

    CELERY_BROKER_URL: str = Field(
        description="URL du broker de messages utilisé par Celery pour distribuer les tâches.",
    )
    CELERY_RESULT_BACKEND: str = Field(
        description="URL du backend de stockage des résultats des tâches Celery.",
    )

    # ------------------------------------------------------------------
    # AWS  stockage d'assets
    # ------------------------------------------------------------------

    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, description="Clé d'accès AWS IAM.")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, description="Clé secrète AWS IAM.")
    AWS_REGION: Optional[str] = Field(default=None, description="Région AWS des ressources utilisées (ex: eu-west-3).")
    AWS_S3_BUCKET: Optional[str] = Field(default=None, description="Nom du bucket S3 utilisé pour stocker les assets créatifs.")


@lru_cache
def get_settings() -> Settings:
    """Retourne l'instance singleton des settings, chargée une seule fois par processus."""
    return Settings()


settings = get_settings()
