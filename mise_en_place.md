LIDIA  Prompts Claude Code + Guides de déploiement
PHASE 1  FONDATION DU PROJET
Prompt 1.1  Structure des dossiers
Tu vas initialiser la structure complète du projet LIDIA, une plateforme 
multi-agents IA pour le marketing digital. 

Crée la structure de dossiers suivante de manière exhaustive et commentée :

lidia/
├── backend/
│   ├── agents/
│   │   ├── orchestrator/
│   │   ├── seo/
│   │   ├── sea/
│   │   ├── content/
│   │   ├── social/
│   │   ├── email/
│   │   ├── analytics/
│   │   ├── reporting/
│   │   └── creative/
│   ├── core/
│   │   ├── state/
│   │   ├── router/
│   │   ├── memory/
│   │   └── graph/
│   ├── llm/
│   │   ├── gateway/
│   │   ├── providers/
│   │   └── router/
│   ├── pytorch_models/
│   │   ├── classifiers/
│   │   ├── embeddings/
│   │   ├── scoring/
│   │   └── anomaly/
│   ├── api/
│   │   ├── routes/
│   │   ├── websocket/
│   │   └── sse/
│   ├── tasks/
│   │   ├── queues/
│   │   └── workers/
│   ├── tools/
│   │   ├── seo/
│   │   ├── sea/
│   │   ├── social/
│   │   ├── email/
│   │   ├── analytics/
│   │   └── creative/
│   ├── db/
│   │   ├── migrations/
│   │   ├── models/
│   │   └── repositories/
│   └── config/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── store/
│   │   ├── services/
│   │   └── types/
│   └── public/
├── infrastructure/
│   ├── docker/
│   ├── prometheus/
│   ├── grafana/
│   └── nginx/
├── scripts/
│   ├── setup/
│   ├── deploy/
│   └── backup/
└── docs/

Pour chaque dossier, crée un fichier __init__.py (Python) ou index.ts 
(TypeScript) vide avec un commentaire décrivant le rôle du module. 
Crée également un fichier README.md à la racine de chaque dossier 
principal décrivant son contenu et ses responsabilités.

Respecte une convention de nommage snake_case pour Python et 
camelCase/PascalCase pour TypeScript. Chaque fichier __init__.py 
doit exporter les composants principaux du module.
Prompt 1.2  Fichiers de configuration et variables d'environnement
Tu vas créer le système de configuration complet du projet LIDIA.

Crée les fichiers suivants :

1. backend/config/settings.py
Un fichier de configuration Pydantic BaseSettings qui charge toutes 
les variables d'environnement avec validation stricte des types. 
Il doit couvrir :

- LLM_MODE : Literal["local", "api", "hybrid"]
- LOCAL_INFERENCE_ENGINE : Literal["ollama", "vllm"]
- LOCAL_DEFAULT_MODEL : str (défaut : "llama3.3:70b")
- LOCAL_FAST_MODEL : str (défaut : "mistral:7b")
- API_PRIMARY_PROVIDER : Literal["groq", "together", "mistral"]
- API_FALLBACK_PROVIDER : Literal["together", "fireworks"]
- API_DEFAULT_MODEL : str
- API_FAST_MODEL : str
- HYBRID_COST_DAILY_LIMIT_USD : float (défaut : 50.0)
- HYBRID_GPU_LOAD_THRESHOLD : float (défaut : 0.8)
- HYBRID_SENSITIVE_TASKS : list[str]
- DATABASE_URL : PostgresDsn
- REDIS_URL : RedisDsn
- QDRANT_HOST : str
- QDRANT_PORT : int (défaut : 6333)
- LANGFUSE_PUBLIC_KEY : str
- LANGFUSE_SECRET_KEY : str
- LANGFUSE_HOST : str
- GROQ_API_KEY : Optional[str]
- TOGETHER_API_KEY : Optional[str]
- MISTRAL_API_KEY : Optional[str]
- FIREWORKS_API_KEY : Optional[str]
- GOOGLE_ADS_DEVELOPER_TOKEN : Optional[str]
- GOOGLE_ADS_CLIENT_ID : Optional[str]
- GOOGLE_ADS_CLIENT_SECRET : Optional[str]
- META_APP_ID : Optional[str]
- META_APP_SECRET : Optional[str]
- FIGMA_ACCESS_TOKEN : Optional[str]
- SERPER_API_KEY : Optional[str]
- SECRET_KEY : str
- DEBUG : bool (défaut : False)
- ENVIRONMENT : Literal["development", "staging", "production"]
- CELERY_BROKER_URL : str
- CELERY_RESULT_BACKEND : str
- AWS_ACCESS_KEY_ID : Optional[str]
- AWS_SECRET_ACCESS_KEY : Optional[str]
- AWS_REGION : Optional[str]
- AWS_S3_BUCKET : Optional[str]

Chaque variable doit avoir une validation Pydantic appropriée, 
un commentaire explicatif, et une valeur par défaut quand c'est 
pertinent. Utilise model_config = SettingsConfigDict(env_file=".env").

2. .env.example
Un fichier d'exemple commenté avec toutes les variables ci-dessus, 
groupées par catégorie (LLM, Base de données, APIs externes, etc.) 
avec des exemples de valeurs et des explications en français.

3. .env.development
Variables pour l'environnement de développement avec LLM_MODE=local, 
DEBUG=True, toutes les URLs pointant vers localhost.

4. .env.production
Template de variables pour la production avec des placeholders 
explicites, LLM_MODE=hybrid, DEBUG=False.

5. backend/config/logging.py
Configuration du logging Python structuré (JSON) avec niveaux 
différents selon l'environnement, rotation des fichiers, et 
intégration avec LangFuse pour le tracing des agents.

Toutes les configurations doivent être importables depuis 
backend/config/__init__.py via un singleton settings.
Prompt 1.3  Docker Compose complet
Tu vas créer le fichier docker-compose.yml complet du projet LIDIA 
avec tous les services de la plateforme.

Le fichier doit définir les services suivants avec leur configuration 
complète (volumes, réseaux, variables d'environnement, healthchecks, 
dépendances, restart policies) :

Services backend :
- langgraph_api : FastAPI + LangGraph, port 8000, dépend de postgres/redis/qdrant
- celery_worker_llm : workers inférence LLM, 2 replicas
- celery_worker_email : workers email Mautic, 2 workers
- celery_worker_social : workers publications sociales, 2 workers
- celery_worker_image : workers Agent Créatif GPU, 1-2 workers
- celery_worker_analytics : worker analytics, 1 worker
- celery_beat : scheduler Celery Beat
- pytorch_models : service FastAPI PyTorch, port 8001
- flower : monitoring Celery, port 5555

Services infrastructure :
- redis : redis:7-alpine, port 6379, avec persistence AOF
- postgres : postgres:16, port 5432, avec volumes persistants
- qdrant : qdrant/qdrant, port 6333 et 6334
- vllm : vllm/vllm-openai (optionnel, profil gpu), port 8080

Services marketing :
- matomo : matomo:latest + matomo_db (mysql:8), ports 8888
- mautic : mautic/mautic + mautic_db (mysql:8), port 8889
- n8n : n8nio/n8n, port 5678, avec volumes persistants
- searxng : searxng/searxng, port 8080
- comfyui : service custom GPU, port 8188

Services monitoring :
- langfuse_web : langfuse/langfuse, port 3001
- langfuse_worker : langfuse/langfuse (worker mode)
- prometheus : prom/prometheus, port 9090
- grafana : grafana/grafana, port 3002
- alertmanager : prom/alertmanager, port 9093
- cadvisor : gcr.io/cadvisor/cadvisor, port 8080
- node_exporter : prom/node-exporter, port 9100

Règles :
- Tous les services partagent un réseau bridge nommé lidia_network
- Les données persistantes sont dans des volumes Docker nommés 
  préfixés lidia_
- Les variables sensibles sont passées via env_file: .env
- Chaque service a un healthcheck approprié
- Les services GPU utilisent le profil "gpu" et le runtime nvidia
- Crée également docker-compose.override.yml pour le développement 
  local avec des overrides appropriés (hot reload, ports exposés, etc.)
- Crée docker-compose.prod.yml pour la production avec les 
  optimisations appropriées (resource limits, logging drivers, etc.)
Prompt 1.4  Requirements et Dockerfiles
Tu vas créer tous les fichiers de dépendances et Dockerfiles du 
projet LIDIA.

1. backend/requirements/base.txt
Dépendances communes à tous les environnements :
- langgraph>=1.0.0
- langchain>=0.3.0
- langchain-community>=0.3.0
- fastapi>=0.115.0
- uvicorn[standard]>=0.32.0
- pydantic>=2.10.0
- pydantic-settings>=2.6.0
- celery[redis]>=5.6.0
- redis>=5.2.0
- psycopg2-binary>=2.9.0
- sqlalchemy>=2.0.0
- alembic>=1.14.0
- qdrant-client>=1.12.0
- litellm>=1.55.0
- langfuse>=3.0.0
- httpx>=0.28.0
- python-multipart>=0.0.18
- python-jose[cryptography]>=3.3.0
- passlib[bcrypt]>=1.7.4
- websockets>=14.0
- sse-starlette>=2.1.0
- structlog>=24.4.0

2. backend/requirements/ml.txt
Dépendances ML/PyTorch :
- torch>=2.5.0
- torchvision>=0.20.0
- transformers>=4.47.0
- sentence-transformers>=3.3.0
- peft>=0.14.0
- accelerate>=1.2.0
- datasets>=3.2.0
- scikit-learn>=1.6.0
- numpy>=2.0.0
- pillow>=11.0.0

3. backend/requirements/dev.txt
Dépendances de développement :
- pytest>=8.3.0
- pytest-asyncio>=0.24.0
- pytest-cov>=6.0.0
- black>=24.10.0
- ruff>=0.8.0
- mypy>=1.13.0
- pre-commit>=4.0.0
- factory-boy>=3.3.0
- httpx[test]>=0.28.0

4. backend/Dockerfile
Dockerfile multi-stage optimisé :
- Stage builder : installation des dépendances
- Stage production : image minimale sans outils de build
- Utilise python:3.11-slim comme base
- Installe requirements/base.txt
- Configure un utilisateur non-root
- Expose le port 8000
- ENTRYPOINT uvicorn

5. backend/Dockerfile.ml
Dockerfile pour le service pytorch_models :
- Base : pytorch/pytorch:2.5.0-cuda12.1-cudnn9-runtime
- Installe requirements/base.txt + requirements/ml.txt
- Configure CUDA_VISIBLE_DEVICES
- Expose le port 8001

6. frontend/package.json
Avec les dépendances :
- react@19, react-dom@19
- typescript@5
- vite@6
- tailwindcss@4
- @shadcn/ui (composants nécessaires)
- recharts@2.14
- zustand@5
- react-query@5
- react-router-dom@7
- lucide-react
- axios
- @types/react, @types/node

7. frontend/Dockerfile
Multi-stage : build Vite puis nginx:alpine pour servir les 
fichiers statiques.

8. infrastructure/nginx/nginx.conf
Configuration nginx comme reverse proxy pour tous les services 
avec rate limiting, SSL ready, et WebSocket support.
PHASE 2  COUCHE MÉMOIRE
Prompt 2.1  Schémas PostgreSQL et migrations Alembic
Tu vas créer le schéma de base de données complet du projet LIDIA 
avec SQLAlchemy 2.0 (style async) et les migrations Alembic.

1. backend/db/models/base.py
Classe de base SQLAlchemy avec :
- UUID comme clé primaire par défaut
- created_at et updated_at automatiques
- Méthode to_dict() pour la sérialisation

2. backend/db/models/  Crée les modèles suivants :

campaigns.py :
- Campaign : id, client_id, name, objective, budget_total, 
  budget_consumed, status (draft/active/paused/completed), 
  channel_allocations (JSONB), start_date, end_date, results (JSONB)
- CampaignCheckpoint : id, campaign_id, agent_name, checkpoint_data 
  (JSONB), created_at

clients.py :
- Client : id, name, industry, website, editorial_guidelines (JSONB),
  brand_colors (JSONB), logo_url, forbidden_topics (ARRAY), 
  target_audience (JSONB)

content.py :
- Content : id, client_id, campaign_id, agent_source, content_type 
  (article/post/email/landing_page/visual), title, body, 
  platform (linkedin/meta/tiktok/email/web), status 
  (draft/review/published/archived), performance_data (JSONB),
  published_at
- ContentTemplate : id, client_id, template_type, structure (JSONB),
  figma_file_id, canva_template_id

keywords.py :
- Keyword : id, client_id, term, search_volume, difficulty, 
  current_position, target_position, cluster (JSONB), last_checked_at
- KeywordHistory : id, keyword_id, position, date

audiences.py :
- Contact : id, client_id, email, first_name, last_name, 
  segment_tags (ARRAY), behavior_data (JSONB), lead_score, 
  last_interaction_at, opted_out
- EmailSequence : id, client_id, contact_id, sequence_name, 
  current_step, status, triggered_at, completed_at

performance.py :
- PerformanceMetric : id, client_id, campaign_id, channel, metric_name,
  metric_value, period_start, period_end
- AgentDecision : id, client_id, agent_name, decision_type, 
  decision_data (JSONB), outcome (JSONB), created_at

users.py :
- User : id, email, hashed_password, role (admin/manager/viewer),
  client_id, is_active, last_login_at

langgraph_checkpoints.py :
- LangGraphCheckpoint : thread_id, checkpoint_id, parent_id, 
  checkpoint_data (JSONB), metadata (JSONB), created_at
(C'est le schéma que PostgresSaver de LangGraph attend)

3. backend/db/migrations/
Configure Alembic avec :
- alembic.ini pointant vers la DATABASE_URL de settings
- env.py async-compatible avec SQLAlchemy async
- Migration initiale create_all_tables générant toutes les tables

4. backend/db/repositories/
Un repository par modèle avec les opérations CRUD async de base 
plus les requêtes spécifiques au domaine. Chaque repository 
hérite d'un BaseRepository[T] générique.

Utilise SQLAlchemy 2.0 style async partout 
(AsyncSession, select(), etc.). Ajoute des index sur toutes 
les colonnes fréquemment filtrées.
Prompt 2.2  Configuration Redis et gestionnaire de session
Tu vas créer la couche d'accès Redis complète du projet LIDIA.

1. backend/core/memory/redis_client.py
Client Redis async avec :
- Pool de connexions configuré depuis settings.REDIS_URL
- Méthodes get, set, delete, expire avec sérialisation JSON auto
- Méthode get_or_set avec TTL pour le caching
- Gestion des erreurs avec retry exponentiel
- Health check endpoint
- Décorateur @cache(ttl=300) pour le caching de fonctions

2. backend/core/memory/session_manager.py
Gestionnaire de sessions des agents avec :
- create_session(agent_name, campaign_id) → session_id
- get_session(session_id) → SessionData
- update_session(session_id, data) → None
- delete_session(session_id) → None
- list_active_sessions() → list[SessionData]

Structure SessionData (Pydantic) :
- session_id, agent_name, campaign_id, client_id
- context : dict (contexte courant de l'agent)
- intermediate_results : dict (résultats partiels du fanout)
- started_at, last_active_at, ttl

TTL par défaut : 24h pour une session active, configurable.

3. backend/core/memory/routing_cache.py
Cache des décisions de routage LiteLLM avec :
- cache_routing_decision(task_hash, provider, model, ttl=300)
- get_routing_decision(task_hash) → Optional[RoutingDecision]
- invalidate_routing_cache() pour forcer un recalcul
- Statistiques de cache hit/miss pour LangFuse

4. backend/tasks/queues/redis_queue.py
Interface de publication dans les queues Celery via Redis :
- enqueue_task(queue_name, task_name, payload, priority) → task_id
- get_task_status(task_id) → TaskStatus
- cancel_task(task_id) → bool
- get_queue_length(queue_name) → int
- Constantes pour les noms de queues : 
  QUEUE_ORCHESTRATION, QUEUE_LLM, QUEUE_IMAGE, 
  QUEUE_EMAIL, QUEUE_SOCIAL, QUEUE_ANALYTICS, QUEUE_SEO

Toutes les opérations doivent être async et utiliser 
redis.asyncio. Inclure des logs structurés sur chaque 
opération importante.
Prompt 2.3  Collections Qdrant et gestionnaire d'embeddings
Tu vas créer la couche de mémoire sémantique du projet LIDIA 
avec Qdrant et les embeddings.

1. backend/core/memory/qdrant_client.py
Client Qdrant avec :
- Connexion depuis settings.QDRANT_HOST et QDRANT_PORT
- Initialisation automatique des collections au démarrage
- Méthodes upsert, search, delete, get par ID
- Gestion des erreurs et retry

2. backend/core/memory/collections.py
Définition et initialisation des collections Qdrant :

COLLECTION_CONTENTS : contenus produits
- vector_size : 768 (sentence-transformers)
- distance : Cosine
- payload_schema : content_id, client_id, content_type, 
  platform, title, created_at, performance_score

COLLECTION_BRAND_KNOWLEDGE : connaissances marque
- vector_size : 768
- payload_schema : client_id, knowledge_type, text, source

COLLECTION_CAMPAIGNS : campagnes passées
- vector_size : 768
- payload_schema : campaign_id, client_id, objective, 
  channels, results_summary, period

COLLECTION_KEYWORDS : clusters SEO
- vector_size : 768
- payload_schema : client_id, keyword, cluster_name, 
  search_volume, difficulty

COLLECTION_AUDIENCES : profils comportementaux
- vector_size : 768
- payload_schema : client_id, segment_name, 
  behavior_pattern, conversion_rate

COLLECTION_VISUAL_REFERENCES : références visuelles
- vector_size : 512 (CLIP embeddings)
- payload_schema : client_id, visual_type, style_tags, 
  file_path, usage_count

Crée une fonction initialize_collections() qui crée toutes 
les collections si elles n'existent pas.

3. backend/core/memory/embedding_manager.py
Gestionnaire d'embeddings avec :
- Classe TextEmbedder utilisant sentence-transformers 
  (paraphrase-multilingual-mpnet-base-v2 pour le français)
- Classe ImageEmbedder utilisant CLIP (openai/clip-vit-base-patch32)
- embed_text(text) → list[float]
- embed_texts(texts) → list[list[float]] (batch)
- embed_image(image_path) → list[float]
- Cache des embeddings fréquents dans Redis (TTL 1h)
- Métriques de latence pour LangFuse

4. backend/core/memory/semantic_search.py
Interface de recherche sémantique de haut niveau :
- search_similar_contents(text, client_id, limit=5) → list[Content]
- search_brand_knowledge(query, client_id, limit=3) → list[Knowledge]
- search_visual_references(brief_text, client_id, limit=5) → list[Visual]
- search_past_campaigns(objective, client_id, limit=3) → list[Campaign]
- upsert_content(content, client_id) → str (point_id)
- upsert_visual(image_path, metadata, client_id) → str (point_id)

Toutes les recherches doivent appliquer un filtre sur client_id 
pour l'isolation multi-tenant.
PHASE 3  COUCHE LLM
Prompt 3.1  LiteLLM gateway
Tu vas créer le gateway LLM central du projet LIDIA avec LiteLLM.

1. backend/llm/gateway/litellm_config.py
Configuration LiteLLM complète :
- Définition des modèles disponibles par provider
- Configuration des fallbacks dans l'ordre :
  Groq → Together AI → Fireworks AI → local vLLM
- Paramètres de retry et timeout par provider
- Budget journalier par provider depuis settings
- Callbacks LangFuse pour le tracing automatique

Structure de configuration :
- Pour le mode local : base_url vers vLLM/Ollama Docker
- Pour le mode api : clés API depuis settings avec fallback chain
- Pour le mode hybrid : les deux configurés simultanément

2. backend/llm/gateway/llm_client.py
Client LLM unifié :
- Classe LIDIALLMClient wrappant LiteLLM
- Méthode complete(prompt, model, task_type, client_id) → str
- Méthode stream(prompt, model, task_type) → AsyncGenerator
- Méthode complete_structured(prompt, model, response_model) 
  → Pydantic model (via instructor)
- Tracking automatique du coût par appel dans Redis
- Injection automatique des métadonnées LangFuse (trace_id, 
  session_id, user_id)
- Gestion des erreurs avec fallback automatique

3. backend/llm/gateway/cost_tracker.py
Tracker de coût LLM en temps réel :
- track_usage(provider, model, input_tokens, output_tokens, cost)
- get_daily_cost() → float
- get_cost_by_agent(agent_name) → dict
- get_cost_by_model(model) → dict
- check_budget_exceeded() → bool
- Stockage dans Redis avec clés TTL 24h
- Alerte automatique via WebSocket si seuil dépassé

4. backend/llm/providers/
Un fichier par provider avec la configuration spécifique :
- groq.py : configuration Groq, modèles disponibles, limites
- together.py : configuration Together AI
- mistral.py : configuration Mistral API
- fireworks.py : configuration Fireworks AI
- vllm.py : configuration vLLM local
- ollama.py : configuration Ollama local

Chaque provider expose une fonction get_provider_config() 
retournant un dict compatible LiteLLM.
Prompt 3.2  Routeur LLM hybride avec PyTorch
Tu vas créer le routeur LLM intelligent du projet LIDIA qui 
décide quel modèle et provider utiliser pour chaque tâche.

1. backend/pytorch_models/classifiers/complexity_classifier.py
Classifieur de complexité de tâche en PyTorch :

Architecture du modèle :
- Entrée : embedding de la tâche (768 dimensions)
- Couche 1 : Linear(768, 256) + ReLU + Dropout(0.3)
- Couche 2 : Linear(256, 64) + ReLU + Dropout(0.2)
- Sortie : Linear(64, 3) → [simple, medium, complex]

Classe ComplexityClassifier(nn.Module) avec :
- forward(x) → logits
- predict(task_description) → Literal["simple", "medium", "complex"]
- Chargement du modèle depuis un checkpoint .pt
- Fallback sur heuristiques si le modèle n'est pas entraîné

Heuristiques de fallback :
- simple : < 50 tokens, classification, extraction
- complex : > 200 tokens, génération longue, raisonnement
- medium : tout le reste

2. backend/pytorch_models/classifiers/trainer.py
Pipeline d'entraînement du classifieur :
- Dataset de tâches marketing labellisées (simple/medium/complex)
- Training loop avec validation
- Sauvegarde du meilleur modèle
- Métriques : accuracy, F1 par classe
- Export vers backend/pytorch_models/checkpoints/

3. backend/llm/router/hybrid_router.py
Routeur hybride principal :

Classe HybridRouter avec méthode route(task) → RoutingDecision :

RoutingDecision (Pydantic) :
- provider : str
- model : str
- reasoning : str
- estimated_cost : float
- fallback_chain : list[str]

Logique de routage dans l'ordre de priorité :
1. Vérification sensibilité des données → forcer local si sensible
2. Vérification charge GPU locale (metric Prometheus) → déborder 
   sur API si > HYBRID_GPU_LOAD_THRESHOLD
3. Vérification budget journalier → basculer local si dépassé
4. Classification de complexité PyTorch → choisir le bon modèle
5. Application du LLM_MODE depuis settings

Table de correspondance task_type → modèle :
- orchestration → llama3.3:70b
- content_generation → qwen3.5:72b
- classification → mistral:7b
- seo_analysis → mistral:7b
- analytics → llama3.3:70b
- reporting → qwen3.5:72b

4. backend/llm/router/sensitivity_detector.py
Détecteur de sensibilité des données :
- Liste de patterns sensibles depuis settings.HYBRID_SENSITIVE_TASKS
- Analyse du contenu de la tâche par regex et mots-clés
- is_sensitive(task_description, task_type) → bool
- Log de chaque décision de sensibilité

5. backend/pytorch_models/api/router_service.py
Service FastAPI exposant le classifieur via HTTP :
- POST /route : reçoit task_description, retourne RoutingDecision
- GET /health : statut du modèle chargé
- GET /metrics : statistiques de routage
Port 8001, déployé comme service Docker indépendant.
PHASE 4  COUCHE ORCHESTRATION
Prompt 4.1  État LangGraph (MarketingState)
Tu vas créer le système d'état central de LangGraph pour 
le projet LIDIA.

1. backend/core/state/marketing_state.py
Définition complète de MarketingState (TypedDict) :

Champs de contexte business :
- objective : str (objectif business en langage naturel)
- client_id : str
- campaign_id : Optional[str]
- budget_total : float
- budget_consumed : float
- channel_allocations : dict[str, float]
- period_start : datetime
- period_end : datetime

Champs de planification orchestrateur :
- weekly_plan : list[PlanItem]
- assigned_tasks : dict[str, list[Task]]
- completed_tasks : list[Task]
- pending_validations : list[HITLRequest]

Champs de résultats agents :
- seo_keywords : list[Keyword]
- seo_audit_results : Optional[dict]
- sea_campaigns : list[CampaignConfig]
- generated_contents : Annotated[list[Content], operator.add]
- published_contents : list[str]
- email_sequences_triggered : list[str]
- analytics_data : Optional[dict]
- performance_summary : Optional[dict]
- visual_assets : list[VisualAsset]

Champs de contrôle de flux :
- active_agent : Optional[str]
- completed_agents : Annotated[list[str], operator.add]
- errors : Annotated[list[AgentError], operator.add]
- alerts : Annotated[list[Alert], operator.add]
- iterations : int
- max_iterations : int (défaut : 5)
- hitl_required : bool
- hitl_response : Optional[dict]
- execution_mode : Literal["planning", "execution", "optimization", "crisis"]

Champs de metadata :
- trace_id : str
- session_id : str
- created_at : datetime
- last_updated_at : datetime

2. backend/core/state/state_models.py
Tous les modèles Pydantic référencés dans MarketingState :
- PlanItem : agent, task_type, priority, deadline, dependencies
- Task : id, agent, type, payload, status, result, error
- HITLRequest : id, agent, action_type, proposal, context, 
  threshold_exceeded, created_at
- Keyword : term, volume, difficulty, position, cluster
- CampaignConfig : name, platform, budget, targeting, creatives
- Content : id, type, platform, title, body, status, metadata
- VisualAsset : id, type, format, file_path, dimensions, style_tags
- AgentError : agent, error_type, message, timestamp, recoverable
- Alert : level, source, message, timestamp, action_required

3. backend/core/state/state_manager.py
Gestionnaire d'état avec :
- create_initial_state(objective, client_id, budget) → MarketingState
- validate_state(state) → list[ValidationError]
- get_state_summary(state) → dict (pour les logs et le monitoring)
- merge_parallel_results(states) → MarketingState 
  (fusion après fanout parallèle)
- check_budget_status(state) → BudgetStatus
- Méthode de sérialisation/désérialisation pour PostgresSaver

4. backend/core/state/validators.py
Validateurs d'état post-fanout :
- validate_parallel_results(state, expected_fields) → ValidationResult
- check_required_fields(state, agent_name) → list[str] (manquants)
- validate_budget_not_exceeded(state) → bool
- validate_iterations_not_exceeded(state) → bool

Toutes les classes Pydantic doivent utiliser model_config 
avec validation stricte. Les TypedDict doivent avoir des 
annotations complètes compatibles avec LangGraph.
Prompt 4.2  Orchestrateur central LangGraph
Tu vas créer l'agent orchestrateur central du projet LIDIA 
avec LangGraph.

1. backend/agents/orchestrator/graph.py
Le graphe LangGraph principal de l'orchestrateur :

Nœuds à définir :
- parse_objective : analyse l'objectif business et initialise l'état
- plan_week : génère le plan hebdomadaire avec les tâches par agent
- route_to_cluster : route vers le bon cluster selon le plan
- fanout_acquisition : Send() vers Agent SEO et Agent SEA en parallèle
- fanout_engagement : Send() vers Content, Social, Email en parallèle
- validate_parallel_results : vérifie que tous les résultats sont présents
- consolidate_results : fusionne les résultats de tous les agents
- check_performance : analyse les performances et décide des ajustements
- reallocate_budget : réalloue le budget selon les performances
- hitl_checkpoint : interrupt() pour validation humaine
- handle_crisis : workflow de gestion de crise
- generate_report : rapport de synthèse
- error_handler : gestion des erreurs et recovery

Arêtes conditionnelles :
- Après route_to_cluster : vers acquisition, engagement, ou mesure
- Après validate_parallel_results : vers consolidate ou error_handler
- Après check_performance : vers reallocate_budget ou hitl_checkpoint
- Après hitl_checkpoint : vers reprise ou arrêt selon réponse humaine
- Boucle d'optimisation avec compteur iterations < max_iterations

Configuration :
- Checkpointer : PostgresSaver depuis settings.DATABASE_URL
- Interrupt points : hitl_checkpoint node
- Récursion limit : 50

2. backend/agents/orchestrator/nodes.py
Implémentation de chaque nœud :

parse_objective_node(state) :
- Appelle le LLM (Llama 3.3 70B) pour décomposer l'objectif
- Extrait : budget, période, canaux prioritaires, KPIs cibles
- Met à jour l'état avec le plan initial

plan_week_node(state) :
- Consulte l'historique PostgreSQL des campagnes similaires
- Génère un plan structuré (list[PlanItem])
- Assigne les tâches à chaque agent
- Calcule les allocations budgétaires initiales

validate_parallel_results_node(state) :
- Vérifie que tous les champs expected sont présents
- En cas de champ manquant : ajoute une alerte et continue sans bloquer

check_performance_node(state) :
- Compare les KPIs actuels aux cibles
- Si écart > 20% : déclenche réallocation
- Si anomalie détectée (via PyTorch) : déclenche alerte

hitl_checkpoint_node(state) :
- Utilise interrupt() de LangGraph
- Prépare le contexte pour l'interface React (proposal, context, options)
- Envoie notification WebSocket

handle_crisis_node(state) :
- Suspend toutes les publications programmées
- Génère une réponse de crise
- Notifie l'équipe

3. backend/agents/orchestrator/prompts.py
Tous les prompts de l'orchestrateur en français, versionnés 
et chargés depuis LangFuse Prompt Management :
- PARSE_OBJECTIVE_PROMPT
- PLAN_WEEK_PROMPT  
- CHECK_PERFORMANCE_PROMPT
- CRISIS_RESPONSE_PROMPT

4. backend/agents/orchestrator/router.py
Fonctions de routage conditionnel :
- should_validate_hitl(state) → Literal["hitl", "continue"]
- route_after_plan(state) → Literal["acquisition", "engagement", "measure", "all"]
- route_after_performance(state) → Literal["reallocate", "hitl", "report"]
- route_after_hitl(state) → Literal["resume", "stop", "modify"]
Prompt 4.3  Subgraphs des trois clusters
Tu vas créer les trois subgraphs de clusters du projet LIDIA.

1. backend/core/graph/acquisition_cluster.py
Subgraph du cluster Acquisition (SEO + SEA) :

Nœuds :
- init_acquisition : initialise l'état du subgraph avec les inputs 
  de l'orchestrateur
- run_seo_agent : exécute le subgraph de l'Agent SEO
- run_sea_agent : exécute le subgraph de l'Agent SEA
- seo_sea_coordinator : coordonne les résultats, détecte les 
  chevauchements mots-clés
- acquisition_reporter : compile les résultats pour l'orchestrateur

État du subgraph AcquisitionState (TypedDict) :
- Hérite des champs pertinents de MarketingState
- Ajoute : seo_brief, sea_brief, coordination_notes

2. backend/core/graph/engagement_cluster.py
Subgraph du cluster Engagement (Content + Social + Email) :

Nœuds :
- init_engagement : initialise avec briefs reçus de l'orchestrateur
- run_content_agent : génère les contenus
- distribute_to_channels : distribue les contenus vers Social et Email
- run_social_agent : adapte et publie sur les réseaux
- run_email_agent : prépare et envoie les séquences
- engagement_reporter : compile les résultats

État EngagementState (TypedDict) :
- content_briefs, generated_contents, social_schedule, 
  email_sequences, channel_results

3. backend/core/graph/measure_cluster.py
Subgraph du cluster Mesure (Analytics + Reporting) :

Nœuds :
- collect_all_metrics : agrège depuis Matomo + APIs
- run_analytics_agent : analyse et détecte les patterns
- detect_anomalies_pytorch : appelle le service PyTorch d'anomaly detection
- run_reporting_agent : génère les rapports
- measure_reporter : retourne les insights à l'orchestrateur

État MeasureState (TypedDict) :
- raw_metrics, analyzed_data, anomalies, report_data, recommendations

4. backend/core/graph/main_graph.py
Assemblage du graphe principal combinant l'orchestrateur 
et les trois subgraphs :
- Compilation du graphe complet avec tous les subgraphs
- Configuration PostgresSaver comme checkpointer
- Définition des interrupt points
- Méthode run(objective, client_id, budget) → AsyncGenerator
  qui stream les mises à jour d'état via WebSocket
- Méthode resume(thread_id, hitl_response) pour reprendre 
  après une validation humaine
- Méthode get_history(thread_id) pour le time-travel

Inclure des tests unitaires pour chaque nœud dans 
tests/agents/orchestrator/ avec des fixtures de MarketingState.
PHASE 5  LES AGENTS SPÉCIALISÉS
Prompt 5.1  Agent SEO
Tu vas créer l'Agent SEO complet du projet LIDIA.

1. backend/agents/seo/graph.py
Graphe LangGraph de l'Agent SEO :

Nœuds :
- load_seo_context : charge l'historique SEO depuis PostgreSQL 
  et les connaissances depuis Qdrant
- research_keywords : recherche et analyse des mots-clés
- audit_technical : audit technique du site client
- analyze_competitors : analyse SERP des concurrents
- generate_briefs : génère les briefs de contenu pour Agent Content
- update_seo_memory : met à jour Qdrant avec les nouvelles données
- seo_reporter : compile et retourne les résultats

2. backend/tools/seo/google_search_console.py
Intégration Google Search Console API :
- Authentification OAuth2 depuis settings
- get_performance_report(site_url, period) → PerformanceData
  (impressions, clics, positions, CTR par page et mot-clé)
- get_index_coverage(site_url) → CoverageData
- get_crawl_errors(site_url) → list[CrawlError]
- Pagination automatique (10 résultats par page depuis sept. 2025)
- Cache Redis 6h pour les données de performance

3. backend/tools/seo/keyword_research.py
Outil de recherche de mots-clés multi-source :
- search_keywords_serper(query) → list[KeywordData]
  (via Serper API si settings.SERPER_API_KEY)
- search_keywords_searxng(query) → list[KeywordData]
  (via SearXNG self-hosted comme fallback)
- analyze_keyword_intent(keyword) → Literal["info", "transactional", "nav"]
- cluster_keywords(keywords) → dict[str, list[str]]
- estimate_difficulty(keyword) → float (0-100)

4. backend/tools/seo/technical_audit.py
Outil d'audit technique via crawl :
- audit_page_speed(url) → SpeedData (via PageSpeed Insights API)
- check_meta_tags(url) → MetaTagAudit
- check_structured_data(url) → StructuredDataAudit
- audit_internal_links(sitemap_url) → InternalLinksAudit
- check_mobile_friendly(url) → bool

5. backend/agents/seo/nodes.py
Implémentation des nœuds avec le modèle Mistral 7B :
- research_keywords_node : prompt structuré pour identifier 
  les opportunités de mots-clés selon l'objectif
- generate_briefs_node : génère des briefs SEO complets 
  (titre, structure, mots-clés cibles, longueur, angle éditorial)
- Output structuré via instructor/Pydantic

6. backend/agents/seo/prompts.py
Prompts versionnés pour l'Agent SEO :
- KEYWORD_RESEARCH_PROMPT
- BRIEF_GENERATION_PROMPT
- COMPETITOR_ANALYSIS_PROMPT
Tous en français, chargés depuis LangFuse.
Prompt 5.2  Agent SEA
Tu vas créer l'Agent SEA complet du projet LIDIA.

1. backend/agents/sea/graph.py
Graphe LangGraph de l'Agent SEA :

Nœuds :
- load_sea_context : charge les campagnes actives et l'historique
- analyze_performance : analyse CPA, ROAS, CTR des campagnes actives
- optimize_bids : ajuste les enchères selon les performances
- generate_ad_variants : génère des variantes d'annonces A/B
- manage_budget : surveille et ajuste l'allocation budgétaire
- detect_anomalies : détecte les dépenses anormales
- sea_reporter : retourne les résultats à l'orchestrateur

2. backend/tools/sea/google_ads.py
Intégration Google Ads API :
- Authentification via OAuth2/Developer Token depuis settings
- get_campaign_performance(customer_id, period) → CampaignPerformance
- update_campaign_bid(campaign_id, new_bid) → bool
- create_responsive_search_ad(campaign_id, ad_data) → str (ad_id)
- get_keyword_performance(campaign_id) → list[KeywordPerformance]
- pause_campaign(campaign_id) → bool
- get_daily_spend(customer_id) → float
- Toutes les opérations loggées avec leur coût estimé

3. backend/tools/sea/meta_ads.py
Intégration Meta Marketing API :
- Authentification via settings.META_APP_ID et META_APP_SECRET
- get_ad_account_insights(account_id, period) → InsightsData
- create_campaign(account_id, campaign_data) → str (campaign_id)
- update_ad_set_budget(adset_id, daily_budget) → bool
- generate_ad_creative(campaign_id, creative_data) → str (creative_id)
- get_audience_insights(account_id, targeting) → AudienceData

4. backend/agents/sea/nodes.py
Implémentation avec Mistral 7B :
- analyze_performance_node : analyse structurée des métriques
- generate_ad_variants_node : génération de 3 variantes d'annonces 
  (titre, description, CTA) par format (search, display, social)
- optimize_bids_node : calcul des enchères optimales selon le CPA cible

5. backend/agents/sea/budget_manager.py
Gestionnaire de budget cross-canal :
- calculate_optimal_allocation(total_budget, channel_performances) 
  → dict[str, float]
- check_daily_pace(campaigns) → PacingStatus
- alert_if_overspending(campaigns, threshold=0.9) → list[Alert]
- Algorithme simple d'allocation proportionnelle au ROAS

6. backend/agents/sea/prompts.py
Prompts SEA en français versionnés LangFuse :
- AD_GENERATION_PROMPT
- BID_OPTIMIZATION_PROMPT
- PERFORMANCE_ANALYSIS_PROMPT
Prompt 5.3  Agent Content
Tu vas créer l'Agent Content complet du projet LIDIA.

1. backend/agents/content/graph.py
Graphe LangGraph de l'Agent Content avec boucle 
Generator-Evaluator :

Nœuds :
- load_content_context : charge la ligne éditoriale depuis Qdrant 
  et PostgreSQL, vérifie les contenus similaires existants
- select_template : sélectionne le format approprié selon le brief
- generate_draft : génère le contenu avec Qwen3.5 72B
- evaluate_quality : évalue le draft (SEO, ton, pertinence)
- evaluate_seo_score : calcule le score SEO du contenu
- refine_content : affine le contenu selon les évaluations
- finalize_content : prépare le contenu final pour publication
- store_content : sauvegarde dans PostgreSQL et Qdrant
- content_reporter : retourne les contenus générés

Arête conditionnelle après evaluate_quality :
- score >= 0.8 : vers finalize_content
- score < 0.8 et iterations < max_iterations : vers generate_draft
- score < 0.8 et iterations >= max_iterations : vers finalize_content 
  quand même (avec flag needs_human_review=True)

2. backend/pytorch_models/scoring/content_scorer.py
Modèle PyTorch de scoring de contenu :

Architecture :
- Entrée : embedding du contenu (768 dim) + features textuelles 
  (longueur, densité mots-clés, lisibilité) concaténées
- Couches : Linear(774, 256) → ReLU → Dropout → Linear(256, 64) 
  → ReLU → Linear(64, 1) → Sigmoid
- Sortie : score 0-1

Classe ContentScorer(nn.Module) avec :
- forward(content_embedding, text_features) → float
- score_content(content_text, target_keywords) → ContentScore
  (score_global, score_seo, score_readability, score_engagement)
- Entraînable sur l'historique de performance des contenus

3. backend/agents/content/nodes.py
Implémentation avec Qwen3.5 72B :
- generate_draft_node : génération avec structured output
  (ContentDraft avec titre, corps, méta-description, hashtags)
- evaluate_quality_node : évaluation via PyTorch scorer + LLM judge
- Feedback loop structuré : le résultat de l'évaluation 
  est injecté dans le prochain prompt de génération

4. backend/tools/content/editorial_guidelines.py
Chargeur de guidelines éditoriales :
- load_guidelines(client_id) → EditorialGuidelines
  (depuis Qdrant par similarité + PostgreSQL pour la structure)
- validate_content_against_guidelines(content, guidelines) 
  → list[Violation]

5. backend/agents/content/prompts.py
Prompts Content en français, versionnés LangFuse :
- ARTICLE_GENERATION_PROMPT (avec variables : brief, keywords, 
  guidelines, similar_contents, evaluation_feedback)
- POST_SOCIAL_GENERATION_PROMPT (par plateforme)
- EMAIL_BODY_GENERATION_PROMPT
- LANDING_PAGE_GENERATION_PROMPT
- CONTENT_EVALUATION_PROMPT
Prompt 5.4  Agent Social
Tu vas créer l'Agent Social complet du projet LIDIA.

1. backend/agents/social/graph.py
Graphe LangGraph de l'Agent Social :

Nœuds :
- load_social_context : charge les métriques d'engagement récents, 
  les tendances détectées, le calendrier existant
- adapt_content_per_platform : adapte le contenu par réseau social
- schedule_publications : détermine les créneaux optimaux 
  selon les données d'engagement historiques
- publish_content : publie via n8n API
- monitor_engagement : collecte les métriques post-publication
- detect_trends : détecte les tendances et mentions via SearXNG
- sentiment_analysis : analyse le sentiment des commentaires/mentions
- crisis_detector : détecte une crise de réputation naissante
- social_reporter : compile les résultats

2. backend/pytorch_models/classifiers/sentiment_classifier.py
Classifieur de sentiment PyTorch multilingue :

Architecture :
- Encoder : distilbert-base-multilingual-cased (HuggingFace) 
  fine-tuné pour le marketing
- Classificateur : Linear(768, 3) → [positif, neutre, négatif]
- Sortie : SentimentResult(label, confidence, is_crisis_signal)

Méthodes :
- analyze_sentiment(text) → SentimentResult
- analyze_batch(texts) → list[SentimentResult]
- detect_crisis_signal(texts, threshold=0.7) → bool

3. backend/tools/social/n8n_client.py
Client n8n pour l'automatisation sociale :
- trigger_workflow(workflow_id, payload) → WorkflowExecution
- get_workflow_status(execution_id) → ExecutionStatus
- get_available_workflows() → list[Workflow]
- Workflows disponibles :
  - LINKEDIN_POST : publication LinkedIn
  - META_POST : publication Facebook/Instagram
  - TIKTOK_POST : publication TikTok
  - SOCIAL_METRICS_COLLECT : collecte des métriques
  - SOCIAL_MENTIONS_MONITOR : surveillance des mentions

4. backend/tools/social/content_adapter.py
Adaptateur de contenu par plateforme :
- adapt_for_linkedin(content) → LinkedInPost
  (3000 chars max, hashtags professionnels, format article si long)
- adapt_for_instagram(content) → InstagramPost
  (2200 chars, 30 hashtags max, ratio image optimal)
- adapt_for_tiktok(content) → TikTokPost
  (script vidéo court, hooks d'accroche, trending sounds suggérés)
- adapt_for_twitter(content) → Tweet (280 chars, thread si nécessaire)

5. backend/agents/social/scheduler.py
Planificateur de publications intelligent :
- get_optimal_slots(platform, client_id, num_slots) 
  → list[datetime]
  (basé sur l'historique d'engagement depuis PostgreSQL)
- avoid_conflicts(schedule, existing_publications) → list[datetime]
- distribute_content_calendar(contents, period) → PublicationCalendar

6. backend/agents/social/prompts.py
Prompts Social en français versionnés LangFuse :
- CONTENT_ADAPTATION_PROMPT par plateforme
- CRISIS_RESPONSE_PROMPT
- TREND_ANALYSIS_PROMPT
Prompt 5.5  Agent Email
Tu vas créer l'Agent Email complet du projet LIDIA.

1. backend/agents/email/graph.py
Graphe LangGraph de l'Agent Email :

Nœuds :
- load_email_context : charge les segments, l'historique des 
  séquences envoyées, les taux d'ouverture/clic depuis PostgreSQL
- segment_audience : segmente les contacts selon les comportements
- select_sequence : sélectionne la séquence appropriée par segment
- generate_email_content : génère les corps d'emails avec Qwen3.5 72B
- optimize_subject_lines : génère et score 3 variantes d'objet
- schedule_send : planifie l'envoi au meilleur moment
- trigger_mautic : déclenche la séquence via Mautic API
- track_results : collecte les métriques post-envoi
- email_reporter : compile les résultats

2. backend/tools/email/mautic_client.py
Client Mautic API complet :
- Authentification OAuth2 depuis settings
- Gestion des contacts :
  create_contact(contact_data) → str (contact_id)
  update_contact(contact_id, data) → bool
  add_contact_to_segment(contact_id, segment_id) → bool
  get_contact_history(contact_id) → list[EmailInteraction]
- Gestion des segments :
  create_segment(name, filters) → str (segment_id)
  get_segment_contacts(segment_id) → list[Contact]
- Gestion des campagnes email :
  create_email_campaign(campaign_data) → str (campaign_id)
  trigger_campaign(campaign_id, contact_ids) → ExecutionResult
  get_campaign_stats(campaign_id) → CampaignStats
- Gestion des emails :
  create_email_template(template_data) → str (email_id)
  send_email(email_id, contact_id) → bool

3. backend/agents/email/segmentation.py
Moteur de segmentation comportementale :
- segment_by_engagement(contacts) → dict[str, list[Contact]]
  Segments : high_engagement, medium_engagement, low_engagement, inactive
- segment_by_purchase_history(contacts) → dict[str, list[Contact]]
  Segments : new, repeat, high_value, at_risk, churned
- segment_by_lead_score(contacts, threshold=50) → dict[str, list[Contact]]
  Segments : hot, warm, cold
- build_custom_segment(contacts, rules) → list[Contact]

4. backend/agents/email/sequence_manager.py
Gestionnaire de séquences d'emails :
- AVAILABLE_SEQUENCES dict avec les séquences prédéfinies :
  welcome : J0, J2, J5, J10 (emails de bienvenue)
  nurturing : J0, J4, J7, J14, J21 (nurturing B2B)
  reactivation : J0, J7, J14 (réactivation inactifs)
  post_purchase : J0, J3, J7 (fidélisation post-achat)
  cart_abandonment : J0, J1, J3 (relance panier)
- get_sequence_for_segment(segment_name) → SequenceConfig
- check_already_received(contact_id, sequence_name) → bool
- calculate_next_send_time(step, optimal_hour) → datetime

5. backend/agents/email/prompts.py
Prompts Email en français versionnés LangFuse :
- EMAIL_BODY_GENERATION_PROMPT (variables : segment, étape, 
  produit, prénom, historique_interactions)
- SUBJECT_LINE_GENERATION_PROMPT (génère 3 variantes)
- REACTIVATION_EMAIL_PROMPT
- WELCOME_SEQUENCE_PROMPT
Prompt 5.6  Agent Analytics
Tu vas créer l'Agent Analytics complet du projet LIDIA.

1. backend/agents/analytics/graph.py
Graphe LangGraph de l'Agent Analytics :

Nœuds :
- collect_matomo_data : collecte les données depuis Matomo API
- collect_campaign_data : collecte les données depuis Google Ads 
  et Meta Ads APIs
- collect_email_data : collecte les stats depuis Mautic API
- collect_social_data : collecte les métriques depuis n8n/APIs sociales
- compute_kpis : calcule tous les KPIs cross-canal
- detect_anomalies_pytorch : appelle le service PyTorch
- attribution_analysis : calcule l'attribution multi-touch
- generate_insights : génère des insights actionnables avec Llama 3.3 70B
- store_metrics : sauvegarde dans PostgreSQL
- analytics_reporter : retourne les résultats à l'orchestrateur

2. backend/pytorch_models/anomaly/anomaly_detector.py
Modèle de détection d'anomalies PyTorch :

Architecture Autoencoder :
- Encoder : Linear(n_features, 64) → ReLU → Linear(64, 16) → ReLU
- Decoder : Linear(16, 64) → ReLU → Linear(64, n_features)
- Détection par reconstruction error (MSE)

Classe AnomalyDetector(nn.Module) avec :
- forward(x) → reconstruction
- compute_anomaly_score(x) → float
- detect(metrics_vector, threshold=None) → AnomalyResult
  (is_anomaly, score, explanation)
- fit(historical_data) : entraînement sur l'historique KPIs
- Seuil automatique basé sur le percentile 95 des scores d'entraînement

3. backend/tools/analytics/matomo_client.py
Client Matomo API :
- get_visits_summary(site_id, period, date) → VisitsSummary
- get_traffic_sources(site_id, period) → TrafficSources
- get_page_performance(site_id, period) → list[PagePerformance]
- get_goals_report(site_id, period) → GoalsReport
- get_ecommerce_report(site_id, period) → Optional[EcommerceReport]
- Authentification par token depuis settings

4. backend/agents/analytics/kpi_calculator.py
Calculateur de KPIs marketing :
- calculate_cac(ad_spend, new_customers) → float
- calculate_ltv(avg_purchase, frequency, margin, churn_rate) → float
- calculate_roas(revenue, ad_spend) → float
- calculate_cpa(total_cost, conversions) → float
- calculate_email_roi(revenue, costs) → float
- calculate_organic_traffic_growth(current, previous) → float
- multi_touch_attribution(touchpoints, conversion_value) 
  → dict[str, float]
  (algorithmes : last_click, first_click, linear, time_decay)
- compile_weekly_scorecard(all_metrics) → WeeklyScorecard

5. backend/agents/analytics/prompts.py
Prompts Analytics en français versionnés LangFuse :
- INSIGHT_GENERATION_PROMPT (avec KPIs, anomalies, contexte historique)
- RECOMMENDATION_PROMPT
- ANOMALY_EXPLANATION_PROMPT
Prompt 5.7  Agent Créatif
Tu vas créer l'Agent Créatif complet du projet LIDIA.

1. backend/agents/creative/graph.py
Graphe LangGraph de l'Agent Créatif :

Nœuds :
- receive_brief : parse et valide le brief visuel reçu
- select_template : sélectionne le template Figma/Canva approprié
- retrieve_style_references : interroge Qdrant pour les références 
  visuelles les plus pertinentes (IPAdapter inputs)
- prepare_comfyui_workflow : construit le workflow ComfyUI JSON
- generate_visual : soumet le workflow à ComfyUI et attend le résultat
- evaluate_visual : évalue la qualité (texte lisible, structure respectée)
- post_process : upscale avec Real-ESRGAN si nécessaire
- store_visual : sauvegarde dans le filesystem + Qdrant (embedding CLIP)
- creative_reporter : retourne le chemin du visuel et les métadonnées

2. backend/tools/creative/comfyui_client.py
Client ComfyUI API :
- submit_workflow(workflow_json) → str (prompt_id)
- get_status(prompt_id) → ComfyUIStatus
- get_output_images(prompt_id) → list[str] (file paths)
- wait_for_completion(prompt_id, timeout=300) → list[str]
- build_flux_workflow(prompt, negative_prompt, width, height, 
  style_reference_paths, controlnet_image_path) → dict (workflow JSON)
- build_lora_workflow(prompt, lora_name, strength) → dict

3. backend/tools/creative/figma_client.py
Client Figma API :
- get_file(file_key) → FigmaFile
- get_components(file_key) → list[FigmaComponent]
- export_frame(file_key, node_id, format="PNG", scale=2) → bytes
- extract_template_structure(file_key, frame_id) → TemplateStructure
  (zones de texte, zones d'image, couleurs, dimensions)
- list_client_templates(client_id) → list[Template]
  (depuis PostgreSQL où les file_keys sont stockés)

4. backend/tools/creative/style_transfer.py
Gestionnaire de transfert de style :
- get_style_references(brief_text, client_id, n=5) 
  → list[StyleReference]
  (interroge Qdrant COLLECTION_VISUAL_REFERENCES)
- prepare_ipadapter_inputs(references) → list[str] (image paths)
- build_controlnet_guidance(template_structure) → str (image path)
  (génère une image de guidance depuis la structure du template)
- upload_reference(image_path, client_id, style_tags) → str (point_id)
  (embed avec CLIP et stocke dans Qdrant)

5. backend/tools/creative/lora_trainer.py
Entraîneur LoRA avec PyTorch + PEFT :
- prepare_dataset(image_paths, captions) → Dataset
- train_lora(base_model, dataset, output_dir, 
  rank=4, alpha=8, epochs=100) → str (lora_path)
  Utilise HuggingFace PEFT + Diffusers pour SDXL
- evaluate_lora(lora_path, test_prompts) → LoRAEvalResult
- export_lora(lora_path, client_id) → str (comfyui_lora_path)
  (copie dans le dossier models/loras de ComfyUI)

6. backend/agents/creative/prompts.py
Prompts Creative en français :
- VISUAL_GENERATION_PROMPT (construit le prompt ComfyUI optimal 
  depuis le brief, les références stylistiques et le template)
- VISUAL_EVALUATION_PROMPT
- BRIEF_PARSER_PROMPT
Prompt 5.8  Agent Reporting
Tu vas créer l'Agent Reporting complet du projet LIDIA.

1. backend/agents/reporting/graph.py
Graphe LangGraph de l'Agent Reporting :

Nœuds :
- load_report_context : charge les données Analytics, les KPIs, 
  les anomalies, les décisions de la semaine
- generate_executive_summary : génère le résumé exécutif 
  en langage naturel avec Qwen3.5 72B
- generate_channel_breakdown : analyse détaillée par canal
- generate_recommendations : recommandations actionnables 
  pour la semaine suivante
- format_report : assemble le rapport final (JSON structuré)
- hitl_before_send : interrupt() pour validation avant envoi
- deliver_report : envoie le rapport via email et/ou API

2. backend/agents/reporting/report_builder.py
Constructeur de rapports structurés :
- build_weekly_report(analytics_data, decisions, kpis) → WeeklyReport
- build_campaign_report(campaign_id) → CampaignReport
- build_crisis_report(crisis_data) → CrisisReport

Modèles Pydantic :
WeeklyReport :
- period, client_id, executive_summary (str)
- kpi_scorecard : dict[str, KPIResult]
- channel_performance : dict[str, ChannelReport]
- top_contents : list[ContentPerformance]
- anomalies_detected : list[AnomalyReport]
- decisions_taken : list[DecisionLog]
- recommendations : list[Recommendation]
- budget_summary : BudgetSummary
- next_week_plan : str

3. backend/agents/reporting/prompts.py
Prompts Reporting en français versionnés LangFuse :
- EXECUTIVE_SUMMARY_PROMPT
- CHANNEL_ANALYSIS_PROMPT
- RECOMMENDATIONS_PROMPT
Chaque prompt inclut des instructions précises sur le format 
attendu (professionnel, actionnable, chiffré) et le ton 
(direct, sans jargon technique excessif).

4. backend/agents/reporting/delivery.py
Système de livraison des rapports :
- send_by_email(report, recipient_emails) → bool
  (via Mautic transactionnel)
- expose_via_api(report) → str (report_url)
  (endpoint REST pour que le frontend récupère le rapport)
- store_report(report, client_id) → str (report_id)
  (dans PostgreSQL + PDF optionnel)
- notify_websocket(report_id, client_id) → None
  (notification temps réel pour le frontend)
PHASE 6  COUCHE INFRASTRUCTURE
Prompt 6.1  Celery workers et configuration des queues
Tu vas créer la configuration Celery complète du projet LIDIA.

1. backend/tasks/celery_app.py
Configuration Celery principale :
- Broker : settings.CELERY_BROKER_URL (Redis)
- Backend : settings.CELERY_RESULT_BACKEND (Redis)
- Sérialisation : JSON + msgpack pour les gros payloads
- Configuration des queues avec priorités :
  orchestration : priority 10 (critique)
  llm_inference : priority 9
  image_generation : priority 5
  email_dispatch : priority 5
  social_publish : priority 5
  analytics : priority 3
  seo_tasks : priority 2
- task_acks_late=True pour éviter la perte de tâches
- worker_prefetch_multiplier=1 pour éviter la starvation
- task_time_limit=600 (10 min max par tâche)
- task_soft_time_limit=540 (alerte à 9 min)
- Configuration de retry avec backoff exponentiel

2. backend/tasks/workers/llm_worker.py
Worker pour les tâches LLM :
- run_agent_task(agent_name, state_dict, thread_id) → dict
  (exécute un sous-graphe LangGraph de manière asynchrone)
- generate_content_task(brief, client_id) → Content
- classify_task_complexity(task_description) → str
  (appelle le service PyTorch)
- Instrumentation LangFuse sur chaque tâche
- Gestion des erreurs avec retry intelligent :
  RateLimitError → retry après 60s
  ContextLengthError → retry avec prompt réduit
  TimeoutError → retry avec modèle plus rapide

3. backend/tasks/workers/image_worker.py
Worker GPU pour l'Agent Créatif :
- generate_visual_task(brief, client_id, campaign_id) → VisualAsset
  (appelle Agent Créatif complet)
- train_lora_task(client_id, image_paths) → str (lora_path)
  (entraînement LoRA en background, peut prendre 30-60 min)
- upscale_image_task(image_path) → str (upscaled_path)
- Vérification GPU disponible avant chaque tâche

4. backend/tasks/workers/marketing_worker.py
Worker pour les tâches marketing temps court :
- publish_social_post_task(content_id, platforms) → dict
- send_email_sequence_task(contact_ids, sequence_name) → dict
- collect_analytics_task(client_id, period) → dict
- audit_seo_task(client_id) → dict
- update_sea_bids_task(client_id) → dict

5. backend/tasks/workers/scheduled_tasks.py
Tâches périodiques via Celery Beat :
- daily_analytics_collection : tous les jours à 6h00
- weekly_seo_audit : tous les lundis à 7h00
- weekly_report_generation : tous les lundis à 8h00
- hourly_sea_performance_check : toutes les heures (heures ouvrées)
- daily_email_sequence_processor : tous les jours à 9h00
- daily_budget_reset : tous les jours à minuit (reset compteurs Redis)
- weekly_memory_cleanup : tous les dimanches à 2h00 
  (supprime les embeddings Qdrant orphelins)

6. backend/tasks/queues/task_monitor.py
Monitoring des queues en temps réel :
- get_queue_depths() → dict[str, int]
- get_worker_stats() → dict[str, WorkerStats]
- get_failed_tasks(queue, limit=100) → list[FailedTask]
- retry_failed_task(task_id) → bool
- Exposition des métriques pour Prometheus
  (custom collector avec queue depths, worker counts, task rates)
Prompt 6.2  LangFuse instrumentation
Tu vas créer l'instrumentation LangFuse complète du projet LIDIA.

1. backend/core/monitoring/langfuse_tracer.py
Traceur LangFuse centralisé :
- Initialisation du client LangFuse depuis settings
- Classe LIDIATracer avec :
  start_trace(name, session_id, user_id, metadata) → Trace
  start_span(trace, name, input_data) → Span
  end_span(span, output_data, usage, model) → None
  log_generation(trace, model, prompt, completion, 
    tokens_used, cost, latency) → None
  score_trace(trace_id, name, value, comment) → None
  log_hitl_event(trace, agent, decision, context) → None
- Décorateur @trace_agent(name, agent_type) pour instrumenter 
  automatiquement les fonctions des agents

2. backend/core/monitoring/langfuse_callbacks.py
Callback LangChain/LangGraph pour le tracing automatique :
- Classe LIDIALangFuseCallback héritant de BaseCallbackHandler
- on_llm_start : log du prompt et du modèle
- on_llm_end : log de la completion, tokens, coût
- on_llm_error : log des erreurs LLM
- on_chain_start/end : tracing des chaînes LangGraph
- on_tool_start/end : tracing des appels d'outils

3. backend/core/monitoring/prompt_manager.py
Gestionnaire de prompts via LangFuse Prompt Management :
- get_prompt(name, version=None) → str
  (avec fallback sur les prompts locaux si LangFuse indisponible)
- update_prompt(name, content, tags) → str (prompt_id)
- list_prompts() → list[PromptInfo]
- Cache local des prompts avec TTL 5 minutes

4. backend/core/monitoring/evaluators.py
Évaluateurs de qualité automatiques :
- evaluate_content_quality(content, target_keywords) → float
  (LLM-as-judge avec Mistral 7B, score 0-1)
- evaluate_email_subject(subject) → float
  (score selon : longueur, personnalisation, urgence, clarté)
- evaluate_ad_copy(ad_text, target_audience) → float
- send_evaluation_to_langfuse(trace_id, evaluator_name, score) → None
- Évaluations déclenchées automatiquement après chaque génération

5. backend/core/monitoring/metrics_exporter.py
Exporteur de métriques custom pour Prometheus :
- Métriques LLM :
  lidia_llm_requests_total (par agent, modèle, provider)
  lidia_llm_tokens_total (par agent, modèle, type)
  lidia_llm_cost_usd_total (par agent, provider)
  lidia_llm_latency_seconds (histogram, par modèle)
- Métriques agents :
  lidia_agent_executions_total (par agent, status)
  lidia_agent_duration_seconds (histogram, par agent)
  lidia_agent_errors_total (par agent, error_type)
- Métriques business :
  lidia_campaigns_active_total (par client)
  lidia_contents_generated_total (par type, platform)
  lidia_hitl_requests_total (par agent, decision)
- Endpoint /metrics exposé sur le port 8000/metrics
Prompt 6.3  Prometheus et Grafana
Tu vas créer la configuration Prometheus et Grafana complète 
du projet LIDIA.

1. infrastructure/prometheus/prometheus.yml
Configuration Prometheus :
- Scrape interval : 15s
- Jobs de scrape pour chaque service :
  job lidia_api : port 8000/metrics (FastAPI + custom metrics)
  job pytorch_models : port 8001/metrics
  job celery_flower : port 5555/metrics
  job redis : port 9121/metrics (redis_exporter)
  job postgres : port 9187/metrics (postgres_exporter)
  job cadvisor : port 8080/metrics
  job node_exporter : port 9100/metrics
  job vllm : port 8080/metrics (si mode local)
- Retention : 30 jours
- Labels globaux : environment, project=lidia

2. infrastructure/prometheus/alerts/
Règles d'alerte par catégorie :

agent_alerts.yml :
- AgentDown : aucune métrique d'agent depuis 5 min → critical
- AgentHighErrorRate : taux d'erreur > 10% sur 10 min → warning
- HITLQueueFull : > 10 validations en attente → warning

llm_alerts.yml :
- LLMCostBudgetExceeded : coût journalier > 80% du seuil → warning
- LLMHighLatency : p95 latence > 30s sur 5 min → warning
- LLMProviderDown : provider primaire indisponible → critical
- LLMTokenRateHigh : > 1M tokens/heure → info

infrastructure_alerts.yml :
- HighCPU : CPU > 85% pendant 5 min → warning
- HighMemory : RAM > 90% → critical
- DiskSpaceLow : disque < 20% → warning
- RedisMemoryHigh : Redis > 80% maxmemory → warning
- PostgresConnectionsHigh : connexions > 80% max → warning
- ContainerRestarting : > 3 restarts en 10 min → critical

3. infrastructure/prometheus/alertmanager.yml
Configuration Alertmanager :
- Route principale vers channel Slack #lidia-alerts
- Route critique (severity=critical) → Slack #lidia-critical + email
- Route business → email équipe marketing
- Inhibit rules : si infrastructure critique, inhiber les alertes agents
- Grouping : 5 min group_wait, 10 min group_interval
- Resolve timeout : 5 min

4. infrastructure/grafana/dashboards/
Trois dashboards JSON provisionnés automatiquement :

operational_dashboard.json :
- Titre : LIDIA  Tableau de bord opérationnel
- Panels : statut de tous les containers, CPU/RAM global, 
  alertes actives, restarts des dernières 24h

llm_dashboard.json :
- Titre : LIDIA  Monitoring LLM
- Panels : tokens/heure par modèle, coût journalier par provider,
  latence p50/p95/p99 par modèle, taux de succès par provider,
  distribution des appels par agent

business_dashboard.json :
- Titre : LIDIA  Tableau de bord Business
- Panels : campagnes actives par client, contenus générés par jour,
  tâches Celery par queue (depth + throughput), 
  validations HITL en attente, budget LLM consommé vs total

5. infrastructure/grafana/datasources.yml
Configuration automatique de la datasource Prometheus 
et des variables de dashboard (environment, client_id).
PHASE 7  API FASTAPI + WEBSOCKET
Prompt 7.1  API FastAPI principale
Tu vas créer l'API FastAPI principale du projet LIDIA.

1. backend/api/main.py
Application FastAPI principale :
- Configuration avec lifespan (startup/shutdown)
- Au startup : initialiser les connections DB, Redis, Qdrant,
  charger les modèles PyTorch, initialiser LangFuse,
  créer les collections Qdrant si absentes,
  lancer les migrations Alembic
- Middleware : CORS, GZip, logging structuré de chaque requête,
  injection du trace_id dans les headers
- Inclusion de tous les routers
- Endpoint /health avec statut de tous les composants
- Endpoint /metrics pour Prometheus
- Gestion globale des exceptions avec format d'erreur standardisé

2. backend/api/routes/campaigns.py
Router campaigns :
- POST /campaigns : créer une campagne (lance le graph LangGraph)
- GET /campaigns : lister les campagnes du client
- GET /campaigns/{id} : détail d'une campagne
- PATCH /campaigns/{id} : modifier objectif/budget
- DELETE /campaigns/{id} : archiver une campagne
- POST /campaigns/{id}/pause : mettre en pause
- POST /campaigns/{id}/resume : reprendre
- GET /campaigns/{id}/history : historique LangGraph (time-travel)

3. backend/api/routes/agents.py
Router agents :
- GET /agents : statut de tous les agents
- GET /agents/{name}/status : statut d'un agent spécifique
- POST /agents/{name}/trigger : déclencher manuellement un agent
- GET /agents/{name}/logs : logs récents de l'agent

4. backend/api/routes/hitl.py
Router validation humaine :
- GET /hitl/pending : liste des validations en attente
- GET /hitl/{id} : détail d'une validation
- POST /hitl/{id}/approve : approuver
- POST /hitl/{id}/reject : rejeter avec commentaire
- POST /hitl/{id}/modify : modifier et approuver
  Chaque action reprend le thread LangGraph via 
  graph.update_state() et graph.invoke()

5. backend/api/routes/content.py
Router contenus :
- GET /contents : lister les contenus (filtres : client, type, status)
- GET /contents/{id} : détail d'un contenu
- PATCH /contents/{id} : modifier manuellement un contenu
- POST /contents/{id}/publish : publier immédiatement
- POST /contents/{id}/schedule : programmer la publication
- GET /contents/calendar : calendrier éditorial

6. backend/api/routes/analytics.py
Router analytics :
- GET /analytics/kpis : KPIs du client sur une période
- GET /analytics/channels : performances par canal
- GET /analytics/anomalies : anomalies détectées
- GET /analytics/reports : liste des rapports générés
- GET /analytics/reports/{id} : rapport complet

7. backend/api/auth.py
Authentification JWT :
- POST /auth/login : génération du token JWT
- POST /auth/refresh : refresh du token
- GET /auth/me : profil utilisateur courant
- Dépendance FastAPI get_current_user pour protéger les routes
- Vérification des rôles (admin, manager, viewer) par route
Prompt 7.2  WebSocket et SSE
Tu vas créer la couche de communication temps réel du projet LIDIA.

1. backend/api/websocket/connection_manager.py
Gestionnaire de connexions WebSocket :
- Classe ConnectionManager avec :
  connect(websocket, client_id, user_id) → str (connection_id)
  disconnect(connection_id) → None
  send_to_user(user_id, message) → None
  send_to_client(client_id, message) → None
  broadcast(message) → None
  get_active_connections_count() → int
- Limite de 100 connexions simultanées
- Heartbeat ping toutes les 30s avec timeout de 60s
- Reconnexion automatique côté serveur si connexion perdue
- Stockage des connexions actives dans Redis (pour multi-instance)

2. backend/api/websocket/events.py
Définition de tous les types d'événements WebSocket :
EventType enum :
- AGENT_STATUS : changement d'état d'un agent
- TASK_PROGRESS : progression d'une tâche Celery
- HITL_INTERRUPT : nouvelle validation humaine requise
- HITL_RESOLVED : validation traitée
- CONTENT_STREAM : token streaming LLM
- ALERT : alerte critique
- BUDGET_UPDATE : mise à jour du budget consommé
- CAMPAIGN_UPDATE : mise à jour d'une campagne
- REPORT_READY : rapport hebdomadaire disponible

Structure WebSocketMessage (Pydantic) :
- event_type : EventType
- campaign_id : Optional[str]
- agent_name : Optional[str]
- payload : dict
- timestamp : datetime
- trace_id : str

3. backend/api/websocket/handlers.py
Handlers WebSocket :
- Endpoint /ws/{client_id} : connexion WebSocket principale
- Authentification via token JWT dans query param
- Dispatch des messages entrants (actions HITL, commandes)
- Envoi des événements sortants (mises à jour temps réel)
- Intégration avec Celery : écoute les événements Celery 
  et les convertit en messages WebSocket

4. backend/api/sse/streams.py
Endpoints SSE pour les flux unidirectionnels :
- GET /sse/content-stream/{generation_id} : 
  stream des tokens LLM en temps réel pendant une génération
- GET /sse/agent-logs/{agent_name} : 
  logs en direct d'un agent spécifique
- GET /sse/campaign-progress/{campaign_id} : 
  progression d'une campagne en cours

Chaque stream SSE :
- Utilise sse-starlette
- Authentification via Authorization header
- Timeout de 5 minutes, heartbeat toutes les 15s
- Format : data: {json}\n\n

5. backend/api/websocket/agent_broadcaster.py
Composant qui écoute les événements LangGraph et Celery 
et les diffuse via WebSocket :
- subscribe_to_langgraph_events() : écoute les transitions de nœuds
- subscribe_to_celery_events() : écoute Celery via event bus
- broadcast_agent_status_change(agent, status) → None
- broadcast_hitl_request(hitl_data) → None
- broadcast_budget_update(client_id, consumed, total) → None
- Tourne comme une coroutine asyncio au démarrage de l'API
PHASE 8  INTERFACE REACT
Prompt 8.1  Foundation React
Tu vas créer la foundation de l'interface React du projet LIDIA.

1. frontend/src/types/index.ts
Tous les types TypeScript correspondant aux modèles backend :
- Campaign, CampaignStatus, ChannelAllocation
- Agent, AgentStatus, AgentType
- Content, ContentType, ContentStatus
- HITLRequest, HITLDecision
- KPIResult, ChannelPerformance, WeeklyReport
- WebSocketMessage, EventType
- User, UserRole
- Alert, AlertLevel
- VisualAsset, Template

2. frontend/src/services/api.ts
Client API centralisé :
- Instance axios avec intercepteurs 
  (injection du JWT, refresh automatique, gestion des erreurs)
- Fonctions pour chaque endpoint du backend :
  campaigns : createCampaign, getCampaigns, getCampaign, 
    pauseCampaign, resumeCampaign
  agents : getAgents, getAgentStatus, triggerAgent
  hitl : getPendingValidations, approveHITL, rejectHITL, modifyHITL
  content : getContents, getContent, publishContent, getCalendar
  analytics : getKPIs, getChannelPerformance, getReports
  auth : login, refreshToken, getMe

3. frontend/src/services/websocket.ts
Service WebSocket :
- Classe WebSocketService (singleton)
- connect(token) → void
- disconnect() → void
- subscribe(eventType, callback) → unsubscribe function
- Reconnexion automatique avec backoff exponentiel
- Gestion du heartbeat
- Queue des messages si connexion perdue (envoyés à la reconnexion)

4. frontend/src/store/
Stores Zustand :
- useCampaignStore : campaigns, currentCampaign, loading, error
- useAgentStore : agents (dict par nom), updating
- useHITLStore : pendingValidations, count
- useAlertStore : alerts, unreadCount, markAsRead
- useAuthStore : user, token, isAuthenticated, login, logout
- useUIStore : sidebarOpen, theme (light/dark), notifications

5. frontend/src/hooks/
Hooks React Query pour la data-fetching :
- useCampaigns() : liste des campagnes avec refetch automatique
- useCampaign(id) : détail d'une campagne
- useAgents() : statut de tous les agents (polling 5s)
- useHITLPending() : validations en attente (polling 10s)
- useKPIs(period) : KPIs de la période
- useCalendar(month) : calendrier éditorial
- useWebSocket() : hook pour s'abonner aux événements WebSocket

6. frontend/src/components/ui/
Composants de base (wrapping shadcn/ui) :
- Badge avec variants pour les statuts agents (active/idle/error/paused)
- StatusIndicator (point coloré animé pour les statuts temps réel)
- MetricCard (KPI avec valeur, variation, trend)
- AgentCard (carte d'agent avec statut et dernière action)
- AlertBanner (bannière d'alerte avec niveau et action)
- LoadingState, ErrorState, EmptyState
- Timeline (affichage chronologique des actions)
Prompt 8.2  Les cinq sections de l'interface
Tu vas créer les cinq sections principales de l'interface 
React du projet LIDIA.

1. frontend/src/pages/Dashboard.tsx
Section 1  Tableau de bord principal :
- Grille de 4 MetricCards en haut : trafic organique, leads, 
  conversions, ROAS (avec variations vs semaine précédente)
- Section "Objectif de la semaine" avec barre de progression
- Section "Budget" : gauge circulaire par canal avec totaux
- Section "Alertes actives" : list des alertes non résolues
- Section "Santé des agents" : 8 AgentCards avec statuts temps réel
- Graphique Recharts : évolution du trafic sur 30 jours (line chart)
- Graphique Recharts : répartition du budget par canal (bar chart)
- Toutes les données via React Query + WebSocket pour les statuts agents

2. frontend/src/pages/AgentControl.tsx
Section 2  Centre de contrôle des agents :
- Visualisation du graphe LangGraph en temps réel
  (composant custom SVG avec nœuds colorés selon statut)
- Fil d'activité en temps réel (WebSocket) : 
  scroll infini des derniers événements avec timestamp et agent source
- Pour chaque agent : carte expandable avec 
  statut courant, tâche en cours (barre progression), 
  dernières 5 actions, prochaines tâches planifiées
- Boutons d'action par agent : Pause, Trigger manuellement
- Onglets par cluster : Acquisition / Engagement / Mesure

3. frontend/src/pages/HITLValidation.tsx
Section 3  Validation humaine :
- Badge counter dans la navigation (nombre de validations en attente)
- Liste des validations en attente (triées par priorité/date)
- Pour chaque validation :
  Header : agent source, type d'action, timestamp
  Contexte : pourquoi l'agent a pausé (markdown rendu)
  Proposition : ce que l'agent veut faire (format structuré)
  Impact estimé : budget, canaux concernés, risques
  Options : Approuver / Rejeter / Modifier avec textarea
- Après décision : confirmation WebSocket de reprise du workflow
- Historique des validations passées avec les décisions prises

4. frontend/src/pages/ContentManagement.tsx
Section 4  Gestion des campagnes et contenus :
4 onglets :

Onglet "Calendrier" :
- Vue mensuelle/hebdomadaire des publications programmées
- Code couleur par plateforme (LinkedIn bleu, Meta rouge, etc.)
- Drag & drop pour reprogrammer
- Clic sur un événement → modal de détail du contenu

Onglet "Bibliothèque" :
- Grid de contenus avec filtres (type, plateforme, statut, client)
- Preview de chaque contenu (texte tronqué + thumbnail si visuel)
- Actions : voir détail, modifier, publier maintenant, archiver
- Indicateurs de performance (vues, clics si publié)

Onglet "Campagnes SEA" :
- Tableau des campagnes actives par plateforme
- Métriques temps réel : dépense du jour, ROAS, CPA, CTR
- Mini line chart de l'évolution du ROAS sur 7 jours
- Bouton pause/reprendre par campagne

Onglet "Visuels" :
- Galerie des visuels générés par l'Agent Créatif
- Upload de templates Figma et affiches de référence
- Status de la génération en cours (SSE stream de progression)

5. frontend/src/pages/Settings.tsx
Section 5  Configuration :
5 sous-sections :

LLM & Modèles :
- Select LLM_MODE (local/api/hybrid) avec description de chaque mode
- Seuils de routage hybride (budget journalier, charge GPU)
- Statut des providers API (vert/rouge selon disponibilité)
- Clés API (champs masqués avec bouton test)

Agents & Automatisation :
- Seuils de déclenchement des validations HITL par agent
  (ex : validation SEA si budget > X€)
- Autonomie par agent : slider 0-100% 
  (0 = tout valider, 100 = pleinement autonome)
- Tâches périodiques : activation/désactivation par tâche Celery Beat

Marque client :
- Upload des affiches de référence stylistique pour l'Agent Créatif
- Upload des templates Figma (saisie du file key)
- Éditeur de ligne éditoriale (tone, keywords interdits, sujets prioritaires)
- Prévisualisation des templates disponibles

Intégrations :
- Statut de connexion de chaque intégration 
  (Google Search Console, Google Ads, Meta, Mautic, Matomo, n8n)
- Bouton de connexion OAuth2 pour chaque service
- Test de connexion avec indicateur de résultat

Utilisateurs :
- Tableau des utilisateurs avec rôles
- Invite d'un nouvel utilisateur
- Modification des droits
Prompt 8.3  Layout et navigation
Tu vas créer le layout principal et la navigation de 
l'interface React du projet LIDIA.

1. frontend/src/components/layout/AppLayout.tsx
Layout principal avec :
- Sidebar fixe à gauche (240px)
- Contenu principal avec header fixe (60px) et zone scrollable
- Responsive : sidebar en drawer sur mobile

2. frontend/src/components/layout/Sidebar.tsx
Navigation latérale :
- Logo LIDIA en haut
- Items de navigation :
  Dashboard (icône LayoutDashboard)
  Agents (icône Bot) + badge statut global (vert si tous OK, rouge si erreur)
  Validations (icône CheckSquare) + badge count des HITL en attente
  Contenus (icône FileText)
  Analytics (icône BarChart2)
  Paramètres (icône Settings)
- En bas : profil utilisateur + bouton logout
- Indicateur "Système actif" avec animation pulse verte/rouge

3. frontend/src/components/layout/Header.tsx
Header avec :
- Titre de la page courante
- Sélecteur de client (si admin multi-clients)
- Cloche de notifications avec dropdown des dernières alertes
- Bouton thème clair/sombre

4. frontend/src/App.tsx
Configuration du routing React Router v7 :
- Routes protégées (RequireAuth wrapper)
- Routes : /, /agents, /validations, /contenus, /analytics, /settings
- Page de login non protégée
- Chargement lazy des pages

5. frontend/src/components/realtime/ActivityFeed.tsx
Composant fil d'activité temps réel :
- Écoute les événements WebSocket (useWebSocket hook)
- Affiche les 50 derniers événements en scroll inversé
- Code couleur par type : vert (succès), orange (warning), 
  rouge (erreur), bleu (info)
- Auto-scroll vers le bas quand nouvel événement
- Pause du scroll si l'utilisateur a scrollé manuellement
- Format : [HH:MM:SS] [AGENT] Message de l'événement

6. frontend/src/components/realtime/AgentGraphVisualizer.tsx
Visualisation SVG du graphe LangGraph en temps réel :
- Représentation SVG des nœuds et arêtes du graphe principal
- Couleurs des nœuds : vert (actif), gris (inactif), 
  orange (en attente HITL), rouge (erreur)
- Animation pulse sur le nœud actif
- Mise à jour via WebSocket (événements AGENT_STATUS)
- Tooltip sur chaque nœud avec la dernière action
- Clic sur un nœud → panel de détail sur la droite

Utilise Tailwind CSS v4 + shadcn/ui pour tous les composants.
Dark mode natif avec les variables CSS de shadcn.
PHASE 9  GUIDES DE DÉPLOIEMENT
GUIDE DE DÉPLOIEMENT  SERVEUR LOCAL
Prompt 9.1  Guide déploiement local
Tu vas créer le guide de déploiement complet sur serveur local 
pour le projet LIDIA.

Crée le fichier docs/deployment/local-server-guide.md avec les 
sections suivantes, de manière exhaustive et opérationnelle :

---

## Prérequis matériels

Configuration minimale recommandée :
- CPU : 16 cœurs (Intel Xeon ou AMD EPYC)
- RAM : 64 GB (128 GB recommandé pour les modèles 70B)
- GPU : NVIDIA RTX 4090 (24 GB VRAM) minimum pour les modèles 70B
  Option sans GPU : mode API uniquement (LLM_MODE=api)
- Stockage : 2 TB NVMe SSD 
  (modèles LLM : ~150 GB, modèles image : ~50 GB, données : le reste)
- Réseau : 1 Gbps minimum, IP statique recommandée

## Prérequis logiciels

Installation dans cet ordre exact :
1. Ubuntu Server 22.04 LTS (recommandé)
2. Docker Engine 27+ et Docker Compose v2
3. NVIDIA Container Toolkit (si GPU)
4. Git, curl, wget
Commandes exactes pour chaque installation.

## Étape 1  Cloner et configurer

- git clone du projet
- Copie de .env.example vers .env
- Guide de remplissage de chaque variable avec des valeurs réelles
- Génération du SECRET_KEY sécurisé
- Configuration du DATABSE_URL, REDIS_URL, QDRANT_HOST

## Étape 2  Téléchargement des modèles LLM

Procédure complète pour télécharger :
- Llama 3.3 70B en GGUF Q4_K_M (via Ollama ou HuggingFace)
- Qwen3.5 72B en GGUF Q4_K_M
- Mistral 7B en GGUF Q4_K_M
- FLUX.2 Schnell (via HuggingFace)
- Qwen-Image
- Modèles sentence-transformers pour les embeddings
Commandes exactes et emplacements des fichiers.

## Étape 3  Lancement du système

- docker compose up -d dans l'ordre correct
- Vérification du démarrage de chaque service (healthchecks)
- Exécution des migrations Alembic
- Initialisation des collections Qdrant
- Vérification que vLLM charge les modèles correctement
- Test de l'endpoint /health de l'API

## Étape 4  Configuration des services marketing

Procédure détaillée pour chaque service :

Matomo :
- Accès à http://localhost:8888
- Installation wizard : base de données, site à tracker
- Création du token API pour les agents
- Configuration du tracking JavaScript à installer sur les sites clients

Mautic :
- Accès à http://localhost:8889
- Configuration SMTP pour l'envoi d'emails (Mailgun, SES, ou SMTP propre)
- Création du compte admin et des tokens OAuth2
- Import de templates d'emails de base

n8n :
- Accès à http://localhost:5678
- Configuration des credentials pour chaque plateforme sociale
- Import des workflows marketing depuis le dossier infrastructure/n8n/

## Étape 5  Configuration des APIs externes

Guide détaillé pour chaque API :

Google Search Console :
- Création d'un projet Google Cloud Console
- Activation de la Search Console API
- Création des credentials OAuth2
- Ajout des variables dans .env

Google Ads :
- Création d'un compte développeur Google Ads
- Demande d'un Developer Token (peut prendre 1-2 semaines)
- Configuration de l'OAuth2 pour les comptes clients
- Test avec l'API de sandbox

Meta Marketing API :
- Création d'une app Meta Business
- Demande des permissions ads_management et ads_read
- Génération des access tokens
- Configuration des Webhooks pour les mises à jour en temps réel

Figma API :
- Création d'un Personal Access Token dans Figma
- Organisation des templates dans des fichiers Figma dédiés par client
- Test d'export via l'API

Serper API :
- Inscription sur serper.dev
- Récupération de la clé API (2500 recherches gratuites/mois)
- Test de la recherche

## Étape 6  Configuration du monitoring

- Accès à Grafana (http://localhost:3002)
- Import automatique des dashboards (déjà configuré via provisioning)
- Configuration des alertes Alertmanager (Slack webhook)
- Accès à LangFuse (http://localhost:3001)
- Création du projet LIDIA dans LangFuse
- Récupération des clés publique/secrète

## Étape 7  Premier lancement d'une campagne test

- Accès à l'interface React (http://localhost:3000)
- Création d'un client test
- Upload d'une affiche de référence pour l'Agent Créatif
- Lancement d'une campagne simple avec un objectif test
- Vérification que le graphe LangGraph s'exécute
- Vérification des traces dans LangFuse

## Maintenance

- Sauvegarde quotidienne des volumes Docker (script scripts/backup/backup.sh)
- Mise à jour des modèles LLM (procédure)
- Rotation des logs
- Commandes de diagnostic utiles
- Résolution des problèmes courants (troubleshooting)
GUIDE DE DÉPLOIEMENT  AWS
Prompt 9.2  Guide déploiement AWS
Tu vas créer le guide de déploiement complet sur AWS 
pour le projet LIDIA.

Crée le fichier docs/deployment/aws-guide.md avec les sections 
suivantes :

---

## Architecture AWS recommandée

Diagramme textuel de l'architecture :
- VPC avec subnets publics et privés
- EC2 instance principale (GPU) dans le subnet privé
- RDS PostgreSQL Multi-AZ dans le subnet privé
- ElastiCache Redis dans le subnet privé
- S3 bucket pour les modèles et les assets
- ALB (Application Load Balancer) dans le subnet public
- Route 53 pour le DNS
- CloudFront en option pour le frontend
- ACM pour les certificats SSL
- Secrets Manager pour les clés API

## Étape 1  Prérequis AWS

- Création d'un compte AWS et configuration d'IAM
- Installation d'AWS CLI v2 et configuration des credentials
- Création d'un utilisateur IAM dédié LIDIA avec les permissions 
  minimales nécessaires (EC2, RDS, ElastiCache, S3, Secrets Manager)
- Configuration du MFA sur le compte

## Étape 2  Infrastructure réseau (VPC)

Commandes AWS CLI exactes pour :
- Création du VPC (10.0.0.0/16)
- Création de 2 subnets publics (10.0.1.0/24, 10.0.2.0/24)
- Création de 2 subnets privés (10.0.3.0/24, 10.0.4.0/24)
- Internet Gateway et NAT Gateway
- Route tables pour chaque subnet
- Security Groups :
  sg_alb : 80, 443 depuis 0.0.0.0/0
  sg_app : 8000, 8001 depuis sg_alb uniquement
  sg_db : 5432 depuis sg_app uniquement
  sg_redis : 6379 depuis sg_app uniquement

## Étape 3  Base de données RDS PostgreSQL

- Création d'une instance RDS PostgreSQL 16
- Instance type recommandé : db.t3.large (2 vCPU, 8 GB) pour démarrer
- Multi-AZ deployment pour la haute disponibilité
- Automated backups : 7 jours de retention
- Parameter group custom (max_connections=200, shared_buffers=2GB)
- Endpoint à utiliser dans DATABASE_URL

## Étape 4  Cache ElastiCache Redis

- Création d'un cluster ElastiCache Redis 7
- Node type : cache.t3.medium pour démarrer
- Cluster mode désactivé (single shard)
- Backup quotidien activé
- Endpoint à utiliser dans REDIS_URL

## Étape 5  Instance EC2 principale

Deux options selon le budget :

Option A  Avec GPU (recommandé pour production) :
- Instance type : g4dn.xlarge (1x T4 16GB VRAM, 4 vCPU, 16 GB RAM)
  ou g4dn.2xlarge (32 GB RAM) si modèles 70B
- AMI : Deep Learning AMI GPU PyTorch 2.x (Ubuntu 22.04)
- EBS : 500 GB gp3 pour les modèles
- EBS supplémentaire : 200 GB gp3 pour les données

Option B  Sans GPU (LLM_MODE=api uniquement) :
- Instance type : t3.2xlarge (8 vCPU, 32 GB RAM)
- AMI : Ubuntu Server 22.04 LTS
- EBS : 200 GB gp3

Configuration commune :
- Elastic IP attachée
- Key pair SSH créé et téléchargé
- IAM Role attaché avec accès S3 et Secrets Manager
- User data script pour l'installation initiale (Docker, NVIDIA toolkit)

## Étape 6  S3 pour les assets

- Création du bucket lidia-models-{account-id} (privé)
- Création du bucket lidia-assets-{account-id} (privé)
- Upload des modèles LLM depuis HuggingFace via script
- Policy de cycle de vie pour archiver les vieux modèles
- Script de sync entre S3 et l'instance EC2 au démarrage

## Étape 7  Secrets Manager

Stockage de tous les secrets dans AWS Secrets Manager :
- lidia/db-credentials : DATABASE_URL complet
- lidia/api-keys : toutes les clés API (Groq, Together, Meta, etc.)
- lidia/app-secrets : SECRET_KEY, JWT secrets

Configuration de l'application pour lire depuis Secrets Manager 
au lieu du fichier .env en production :
- IAM Role avec accès secretsmanager:GetSecretValue
- Script Python de chargement des secrets au démarrage

## Étape 8  Application Load Balancer

- Création de l'ALB dans les subnets publics
- Target group pointant vers le port 8000 de l'EC2
- Target group pointant vers le port 3000 (frontend)
- Listener HTTPS (443) avec certificat ACM
- Redirect HTTP → HTTPS
- Health check sur /health
- WebSocket support activé (sticky sessions ou stickiness désactivée)

## Étape 9  Déploiement de l'application

Sur l'instance EC2 :
- git clone du projet
- Configuration des variables d'environnement 
  (chargées depuis Secrets Manager)
- Utilisation de docker-compose.prod.yml
- Commandes de démarrage dans l'ordre correct
- Exécution des migrations Alembic
- Configuration de systemd pour le redémarrage automatique

## Étape 10  Configuration DNS et SSL

- Création d'un hosted zone Route 53 pour le domaine
- Record A → ALB DNS name
- Certificat ACM validé par DNS
- Configuration du domaine dans les variables d'environnement 
  (CORS, ALLOWED_HOSTS)

## Étape 11  Monitoring AWS natif

En complément de Prometheus/Grafana :
- CloudWatch Logs : redirection des logs Docker vers CloudWatch
- CloudWatch Alarms : CPU > 80%, RAM > 85%, RDS connections > 80%
- SNS Topic pour les notifications d'alarme par email
- AWS Health Dashboard pour les incidents de service

## Coûts estimés mensuels

Tableau des coûts AWS estimés par configuration :

| Service | Configuration starter | Configuration prod |
|---|---|---|
| EC2 g4dn.xlarge | ~380$/mois | ~760$/mois (reserved) |
| RDS db.t3.large Multi-AZ | ~180$/mois | ~360$/mois |
| ElastiCache t3.medium | ~70$/mois | ~140$/mois |
| ALB | ~25$/mois | ~50$/mois |
| S3 + transfer | ~20$/mois | ~50$/mois |
| NAT Gateway | ~45$/mois | ~90$/mois |
| Route 53 | ~1$/mois | ~5$/mois |
| Total estimé | ~721$/mois | ~1455$/mois |

Notes sur les Reserved Instances (réduction de 30-60%) 
et Savings Plans pour réduire les coûts.

## Étape 12  CI/CD avec GitHub Actions

Workflow de déploiement automatique :
- Push sur main → build des images Docker
- Push des images sur ECR (Elastic Container Registry)
- SSH sur l'EC2 → docker compose pull → docker compose up -d
- Smoke tests automatiques post-déploiement
- Rollback automatique si les healthchecks échouent

Crée le fichier .github/workflows/deploy.yml complet.

## Sécurité et conformité

- Activation de AWS GuardDuty pour la détection de menaces
- AWS Config pour l'audit de la configuration
- Rotation automatique des secrets via Secrets Manager
- VPC Flow Logs activés
- CloudTrail pour l'audit de toutes les actions API AWS
- Chiffrement EBS et RDS au repos (KMS)
- Security Groups avec principe du moindre privilège

## Disaster Recovery

- RPO (Recovery Point Objective) : 24h (backups RDS quotidiens)
- RTO (Recovery Time Objective) : 2h (procédure de restauration)
- Procédure de restauration complète pas à pas
- Test de DR recommandé : trimestriel

## Troubleshooting AWS

Problèmes courants et solutions :
- Instance EC2 inaccessible : vérification des Security Groups et NACLs
- RDS timeout : vérification des connexions max et du subnet
- GPU non détecté par Docker : NVIDIA Container Toolkit
- WebSocket timeouts via ALB : configuration idle timeout à 3600s
- Coût S3 élevé : vérification des requêtes et mise en place du lifecycle

Le trou est réel. Voici les choix arrêtés et leur justification.

Pour le texte (COLLECTION_CONTENTS, COLLECTION_BRAND_KNOWLEDGE, etc.)

Le choix retenu est intfloat/multilingual-e5-large. Voici pourquoi il bat paraphrase-multilingual-mpnet-base-v2 dans notre contexte :

Critère	multilingual-e5-large	paraphrase-multilingual-mpnet-base-v2
Dimensions	1024	768
Score MTEB français	62.3	53.1
Support query/passage	Natif (préfixe "query:" et "passage:")	Non
Taille mémoire	~560MB	~420MB
Latence batch 32	~45ms GPU	~30ms GPU

Le préfixe query/passage de E5 est décisif pour notre cas d'usage : quand l'Agent Content cherche "est-ce qu'un article similaire existe", c'est une requête sémantique contre un corpus de documents. E5 est conçu pour ça, mpnet est conçu pour la similarité phrase-à-phrase symétrique.

La dimension passe donc de 768 à 1024 dans toutes les collections Qdrant textuelles. Ça impacte le prompt 2.3 (collections.py) : vector_size passe à 1024 pour COLLECTION_CONTENTS, COLLECTION_BRAND_KNOWLEDGE, COLLECTION_CAMPAIGNS, COLLECTION_KEYWORDS, COLLECTION_AUDIENCES.

Pour les images (COLLECTION_VISUAL_REFERENCES)

Le choix retenu est ViT-SO400M-14-SigLIP-384 de Google. Voici pourquoi il bat CLIP ViT-L/14 :

Critère	SigLIP SO400M	CLIP ViT-L/14
Dimensions	1152	768
Zero-shot ImageNet	83.1%	75.3%
Similarité texte-image	Supérieur	Référence
Licence	Apache 2.0	MIT
Taille	~1.9GB	~890MB

SigLIP utilise une loss sigmoid au lieu de softmax  ce qui le rend plus robuste sur des comparaisons de paires isolées, exactement ce qu'on fait quand on compare un brief textuel à une affiche de référence.

La dimension de COLLECTION_VISUAL_REFERENCES passe de 512 à 1152.

Conséquence sur embedding_manager.py

Les deux embedders sont définis précisément :

TextEmbedder :
  model : intfloat/multilingual-e5-large
  dimension : 1024
  encode_query(text) : préfixe "query: " + text
  encode_passage(text) : préfixe "passage: " + text
  batch_size : 32

ImageEmbedder :
  model : google/siglip-so400m-patch14-384
  dimension : 1152
  processor : SiglipProcessor
  encode_image(image_path) → list[float]
  encode_text_for_image_search(text) → list[float]
    (SigLIP encode texte et image dans le même espace)
Deuxième point  Le GPU partagé LLM + images

Tu as raison, "GPU partagé si possible" est une note vague qui cache une décision d'infrastructure non prise. Voici la décision explicite avec les trois scénarios réels.

La réalité des chiffres sur un GPU 24GB (RTX 4090)

Modèle	VRAM nécessaire (Q4)
Llama 3.3 70B	~40GB → impossible sur 24GB seul
Llama 3.3 70B Q4_K_M	~38GB → impossible
Qwen3.5 72B Q4_K_M	~40GB → impossible
Mistral 7B Q4_K_M	~4.5GB → faisable
FLUX.2 Schnell	~8GB
Qwen-Image	~12GB
SigLIP SO400M	~1.9GB
E5-large	~0.56GB

Conclusion immédiate : les modèles 70B ne tiennent pas sur un seul GPU 24GB. Ils nécessitent soit du tensor parallelism sur 2+ GPUs, soit une quantisation plus agressive (Q2 ou Q3, avec perte de qualité), soit le mode API uniquement.

Les trois scénarios d'infrastructure  décision explicite

Scénario A  Un seul GPU 24GB (RTX 4090 ou équivalent)

Seuls les modèles légers tournent en local. Mistral 7B pour les tâches simples. Les tâches complexes (Llama 70B, Qwen 72B) passent obligatoirement en mode API. La génération d'images tourne en séquentiel avec swap : vLLM est mis en pause, FLUX.2 est chargé, génère, est déchargé, vLLM reprend. Latence de swap : 10-30 secondes. Acceptable pour la génération d'images (tâche non temps-réel dans Celery). LLM_MODE doit être "api" ou "hybrid" dans ce scénario.

Scénario B  Deux GPUs 24GB (2x RTX 4090)

GPU 0 : vLLM avec tensor parallelism (--tensor-parallel-size 2) pour Llama 70B et Qwen 72B. Les deux GPUs en parallèle permettent de charger les modèles 70B en Q4_K_M (~38-40GB répartis sur 48GB total). GPU 1 (partagé avec GPU 0 pour le LLM) : quand vLLM ne génère pas activement, ComfyUI emprunte VRAM sur GPU 1 pour FLUX.2. Cette cohabitation est gérée par CUDA_VISIBLE_DEVICES et des réservations VRAM dans vLLM (--gpu-memory-utilization 0.70 pour laisser 30% à ComfyUI sur GPU 1). C'est le scénario recommandé pour self-hosting complet.

Scénario C  GPU 24GB + location GPU à la demande (RunPod/Vast.ai)

GPU local 24GB : vLLM avec les modèles légers (Mistral 7B) + les modèles d'embedding (E5-large, SigLIP). GPU loué à la demande : les tâches de génération d'images sont envoyées vers un container RunPod avec FLUX.2 préchargé. RunPod expose une API ComfyUI, notre Agent Créatif l'appelle exactement comme il appellerait ComfyUI local. Coût : ~0.30-0.69$/heure, facturé à la minute, uniquement quand on génère. Pour un client qui génère 10-20 visuels par semaine, c'est l'option la plus économique.

La logique de swap pour Scénario A

Quand un seul GPU est disponible, le ModelSwapManager gère l'accès séquentiel. Il expose deux méthodes : acquire_for_llm() décharge ComfyUI si chargé, libère la VRAM, notifie vLLM qu'il peut charger le modèle demandé. acquire_for_image() envoie un signal SIGTERM gracieux à vLLM pour libérer la VRAM, attend la confirmation, charge FLUX.2 dans ComfyUI. Le tout est coordonné par une queue de priorité dans Redis : les tâches LLM ont priorité sur les tâches image. La latence de swap est loggée dans LangFuse et exposée dans Grafana pour détecter si le swap devient un goulot d'étranglement.

Décision finale pour le stack

Le Docker Compose doit avoir trois profils GPU explicites :

profil single-gpu :
  vllm : --tensor-parallel-size 1, models Mistral 7B uniquement
  comfyui : CUDA_VISIBLE_DEVICES=0, swap géré par ModelSwapManager
  LLM_MODE forcé à "hybrid" (local pour les tâches légères, API pour 70B)

profil dual-gpu :
  vllm : --tensor-parallel-size 2, CUDA_VISIBLE_DEVICES=0,1
  comfyui : CUDA_VISIBLE_DEVICES=1, --gpu-memory-utilization 0.30
  LLM_MODE peut être "local" complet

profil api-only (sans GPU) :
  vllm : absent du compose
  comfyui : CPU mode (lent mais fonctionnel pour tests)
  LLM_MODE forcé à "api"

Ce sont trois fichiers docker-compose distincts ou trois profils Docker Compose (--profile single-gpu / --profile dual-gpu / --profile api-only) à ajouter en mise à jour 8 des prompts Claude Code.

MISE À JOUR 8  Modèles d'embedding précis
Le projet LIDIA est déjà initialisé avec ses phases 1 à 9
et les mises à jour 1 à 7.
Tu vas maintenant corriger et préciser la couche d'embedding
dans toute la base de code. Le trou architectural identifié :
aucun modèle d'embedding n'était explicitement défini.

Les modèles retenus sont :
- Texte : intfloat/multilingual-e5-large (dimension 1024)
- Images : google/siglip-so400m-patch14-384 (dimension 1152)

Ces choix impactent les dimensions des collections Qdrant,
le code d'embedding, et les requirements.

1. backend/requirements/ml.txt
MODIFICATION : précise les versions des modèles d'embedding.

Ajoute sans supprimer l'existant :
- sentence-transformers>=3.3.0 (déjà présent  garde-le)
- transformers>=4.47.0 (déjà présent  garde-le)
- einops>=0.8.0 (requis par SigLIP SO400M)
- open-clip-torch>=2.26.1 (backend alternatif CLIP si SigLIP indisponible)

2. backend/core/memory/embedding_manager.py
REMPLACEMENT COMPLET du fichier existant.

Le fichier existant définissait des embedders génériques
sans modèle précis. Remplace-le entièrement par :

--- Constantes de configuration ---

TEXT_EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
TEXT_EMBEDDING_DIM = 1024
TEXT_EMBEDDING_BATCH_SIZE = 32

IMAGE_EMBEDDING_MODEL = "google/siglip-so400m-patch14-384"
IMAGE_EMBEDDING_DIM = 1152
IMAGE_EMBEDDING_BATCH_SIZE = 16

--- Classe TextEmbedder ---

Classe TextEmbedder avec :
- __init__() :
  Charge intfloat/multilingual-e5-large via SentenceTransformer
  Paramètre device : "cuda" si torch.cuda.is_available() sinon "cpu"
  Paramètre trust_remote_code=False (modèle public, pas besoin)
  Log du modèle chargé et du device dans structlog

- encode_query(text: str) → list[float]
  Préfixe "query: " + text avant l'encoding
  Normalise le vecteur (normalize_embeddings=True)
  Retourne list[float] de dimension 1024
  Usage : quand l'agent cherche dans Qdrant

- encode_passage(text: str) → list[float]
  Préfixe "passage: " + text avant l'encoding
  Normalise le vecteur
  Retourne list[float] de dimension 1024
  Usage : quand on stocke un document dans Qdrant

- encode_passages_batch(texts: list[str]) → list[list[float]]
  Préfixe "passage: " sur chaque texte
  Encode en batch de TEXT_EMBEDDING_BATCH_SIZE
  Progress bar tqdm pour les gros batches
  Retourne list[list[float]]

- encode_queries_batch(texts: list[str]) → list[list[float]]
  Même chose avec préfixe "query: "

- get_cache_key(text: str, mode: Literal["query", "passage"]) → str
  SHA256 du texte + mode → clé Redis pour le cache

Cache Redis sur encode_query et encode_passage :
  TTL : 3600 secondes (1 heure)
  Clé : "lidia:embed:text:{cache_key}"
  Sérialisation : JSON (list[float])
  Si cache hit → retourne directement sans appel au modèle
  Log cache hit/miss dans LangFuse (métrique embedding_cache_hit)

--- Classe ImageEmbedder ---

Classe ImageEmbedder avec :
- __init__() :
  Charge google/siglip-so400m-patch14-384 via AutoModel et AutoProcessor
  from transformers import AutoProcessor, AutoModel
  device = "cuda" si disponible sinon "cpu"
  Le modèle est chargé en float16 si cuda, float32 sinon
  (torch_dtype=torch.float16 si cuda pour économiser la VRAM)

- encode_image(image_path: str) → list[float]
  Charge l'image avec PIL.Image.open()
  Passe par processor(images=image, return_tensors="pt")
  Forward pass dans le modèle → image_embeds
  Normalise : F.normalize(image_embeds, dim=-1)
  Retourne list[float] de dimension 1152

- encode_images_batch(image_paths: list[str]) → list[list[float]]
  Encode en batch de IMAGE_EMBEDDING_BATCH_SIZE
  Gestion des erreurs par image (skip et log si image corrompue)
  Retourne list[list[float]]

- encode_text_for_image_search(text: str) → list[float]
  SigLIP encode texte et image dans le même espace vectoriel.
  Passe par processor(text=[text], return_tensors="pt")
  Forward pass → text_embeds
  Normalise → list[float] de dimension 1152
  Usage : quand l'Agent Créatif cherche des références visuelles
  avec un brief textuel dans COLLECTION_VISUAL_REFERENCES

Cache Redis sur encode_image :
  TTL : 86400 secondes (24 heures  les images changent rarement)
  Clé : "lidia:embed:image:{sha256_du_chemin_image}"

--- Classe EmbeddingManager (façade) ---

Classe EmbeddingManager singleton avec :
- text : TextEmbedder (instancié au démarrage)
- image : ImageEmbedder (instancié au démarrage)

Méthodes de convenance qui délèguent :
- embed_for_storage(text) → encode_passage(text)
- embed_for_search(text) → encode_query(text)
- embed_image(path) → encode_image(path)
- embed_text_for_visual_search(text) → encode_text_for_image_search(text)

Propriétés statiques :
- TEXT_DIM = 1024
- IMAGE_DIM = 1152

Initialisation dans backend/api/main.py au startup :
embedding_manager = EmbeddingManager()
app.state.embedding_manager = embedding_manager

3. backend/core/memory/collections.py
MODIFICATION : met à jour les dimensions de toutes les collections.

Dans initialize_collections(), modifie les vector_size :

COLLECTION_CONTENTS :
  Avant : vector_size = 768
  Après : vector_size = 1024  (intfloat/multilingual-e5-large)

COLLECTION_BRAND_KNOWLEDGE :
  Avant : vector_size = 768
  Après : vector_size = 1024

COLLECTION_CAMPAIGNS :
  Avant : vector_size = 768
  Après : vector_size = 1024

COLLECTION_KEYWORDS :
  Avant : vector_size = 768
  Après : vector_size = 1024

COLLECTION_AUDIENCES :
  Avant : vector_size = 768
  Après : vector_size = 1024

COLLECTION_VISUAL_REFERENCES :
  Avant : vector_size = 512  (CLIP générique)
  Après : vector_size = 1152 (SigLIP SO400M)
  Note dans le commentaire : les vecteurs texte pour la recherche
  visuelle utilisent aussi IMAGE_DIM = 1152 car SigLIP partage
  le même espace pour texte et image.

Ajoute dans initialize_collections() une vérification au démarrage :
  Si une collection existe avec une dimension différente de celle
  attendue → log une erreur critique et lève une ValueError
  avec le message : "Collection {name} dimension mismatch :
  expected {expected_dim}, found {existing_dim}.
  Drop and recreate the collection manually or run migration."
  Cela évite les erreurs silencieuses si le code est mis à jour
  sur une instance Qdrant existante avec les anciennes dimensions.

4. backend/core/memory/semantic_search.py
MODIFICATION : utilise correctement encode_query vs encode_passage.

Dans chaque fonction de recherche, remplace les appels génériques
embed_text() par les appels spécialisés :

search_similar_contents(text, client_id, limit=5) :
  Utilise embedding_manager.embed_for_search(text)
  (encode_query  on cherche)

upsert_content(content, client_id) :
  Utilise embedding_manager.embed_for_storage(content.body)
  (encode_passage  on stocke)

search_brand_knowledge(query, client_id, limit=3) :
  Utilise embedding_manager.embed_for_search(query)

upsert_brand_knowledge(text, client_id) :
  Utilise embedding_manager.embed_for_storage(text)

search_visual_references(brief_text, client_id, limit=5) :
  Utilise embedding_manager.embed_text_for_visual_search(brief_text)
  (SigLIP encode le texte dans l'espace image)

upsert_visual(image_path, metadata, client_id) :
  Utilise embedding_manager.embed_image(image_path)
  (SigLIP encode l'image)

5. backend/pytorch_models/api/router_service.py
MODIFICATION : ajoute les routes de monitoring des embeddings.

GET /embeddings/health → EmbeddingHealthStatus
  (text_model_loaded: bool, image_model_loaded: bool,
   text_model_name: str, image_model_name: str,
   text_dim: int, image_dim: int,
   text_cache_hit_rate_pct: float,
   image_cache_hit_rate_pct: float)

GET /embeddings/test
  Accepte un JSON {"text": "...", "image_path": "..."}
  Retourne les embeddings calculés (utile pour le debug)
  Protégé par authentification admin uniquement

6. backend/core/monitoring/metrics_exporter.py
MODIFICATION : ajoute les métriques d'embedding dans Prometheus.

Ajoute les métriques custom :
lidia_embedding_requests_total (par type: text/image, par mode: query/passage)
lidia_embedding_cache_hits_total (par type: text/image)
lidia_embedding_latency_seconds (histogram, par type)
lidia_embedding_batch_size (histogram)

Ces métriques apparaissent dans le dashboard Grafana LLM
(nouveau panel "Embeddings" dans llm_dashboard.json).

7. scripts/setup/download_models.sh
NOUVEAU : script de téléchargement de tous les modèles au setup.

Script bash qui télécharge dans l'ordre :
1. Modèles LLM (via HuggingFace CLI ou ollama pull)
2. intfloat/multilingual-e5-large (via huggingface-cli download)
3. google/siglip-so400m-patch14-384 (via huggingface-cli download)
4. Modèles image : FLUX.2 Schnell, Qwen-Image (via HuggingFace)
5. Vérifie les checksums SHA256 de chaque modèle téléchargé

Variables d'environnement attendues :
HUGGINGFACE_TOKEN (pour les modèles nécessitant une authentification)
MODELS_PATH (répertoire de destination)

Affiche la progression et l'espace disque disponible à chaque étape.
Estime l'espace disque requis avant de commencer (~280GB total).
MISE À JOUR 9  Profils GPU Docker et ModelSwapManager
Le projet LIDIA est déjà initialisé avec ses phases 1 à 9
et les mises à jour 1 à 8.
Tu vas maintenant implémenter la gestion explicite des 
configurations GPU avec trois profils Docker Compose distincts
et un ModelSwapManager pour le scénario à GPU unique.

La note vague "GPU partagé si possible" est remplacée par
une architecture explicite avec trois scénarios documentés.

1. docker-compose.yml
MODIFICATION : ajoute les profils GPU aux services concernés.

Service vllm :
  profiles: ["single-gpu", "dual-gpu"]
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            capabilities: [gpu]
            device_ids: ["0"]  # GPU 0 toujours pour vLLM

  Ajoute deux variantes de commande selon le profil :
  Profil single-gpu :
    --model mistral:7b
    --tensor-parallel-size 1
    --gpu-memory-utilization 0.65
    (laisse 35% de VRAM pour le swap avec ComfyUI)
    --max-model-len 16384
    --served-model-name lidia-base

  Profil dual-gpu :
    --model ${LOCAL_DEFAULT_MODEL}
    --tensor-parallel-size 2
    --gpu-memory-utilization 0.85
    --max-model-len 32768
    (utilise GPU 0 et 1 pour les modèles 70B)
    CUDA_VISIBLE_DEVICES=0,1

Service comfyui :
  profiles: ["single-gpu", "dual-gpu"]
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            capabilities: [gpu]
            device_ids: ["0"]  # même GPU que vLLM en single-gpu

  Variables d'environnement par profil :
  Profil single-gpu :
    GPU_SWAP_ENABLED=true
    GPU_SWAP_MANAGER_URL=http://langgraph_api:8000/internal/gpu-swap
    COMFYUI_VRAM_LIMIT_GB=12
    (ComfyUI attend le signal du ModelSwapManager avant de charger)

  Profil dual-gpu :
    GPU_SWAP_ENABLED=false
    CUDA_VISIBLE_DEVICES=1
    COMFYUI_VRAM_LIMIT_GB=20
    (ComfyUI a GPU 1 pour lui seul)

Service pytorch_models :
  profiles: ["single-gpu", "dual-gpu", "api-only"]
  (le service pytorch_models tourne sur CPU en api-only)
  Variables d'environnement :
    PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
    Profil single-gpu : CUDA_VISIBLE_DEVICES=0
    Profil dual-gpu : CUDA_VISIBLE_DEVICES=1
    Profil api-only : CUDA_VISIBLE_DEVICES="" (CPU only)

2. docker-compose.single-gpu.yml
NOUVEAU fichier override pour le profil single-gpu.

Override du service vllm :
  Commande complète avec Mistral 7B uniquement
  gpu-memory-utilization: 0.65
  Variables d'env : LLM_MODE_OVERRIDE=hybrid
  (force le mode hybrid même si settings dit local)

Override du service langgraph_api :
  Variables d'env supplémentaires :
    GPU_PROFILE=single-gpu
    VLLM_MODELS_AVAILABLE=mistral:7b
    IMAGE_GENERATION_MODE=swap
    GPU_SWAP_LOCK_TTL=120
    (lock Redis tenu 120 secondes maximum par swap)

Override du service comfyui :
  resource_limits: memory 4g
  Variables d'env : GPU_SWAP_ENABLED=true

3. docker-compose.dual-gpu.yml
NOUVEAU fichier override pour le profil dual-gpu.

Override du service vllm :
  Commande avec tensor-parallel-size 2
  CUDA_VISIBLE_DEVICES=0,1
  Modèles 70B disponibles

Override du service comfyui :
  CUDA_VISIBLE_DEVICES=1
  GPU_SWAP_ENABLED=false
  (pas de swap nécessaire, GPU dédié)

Override du service pytorch_models :
  CUDA_VISIBLE_DEVICES=1
  (partage GPU 1 avec ComfyUI, acceptable car
   les tâches pytorch_models sont rarement concurrentes
   avec la génération d'images)

4. docker-compose.api-only.yml
NOUVEAU fichier override pour le profil sans GPU.

Supprime les services vllm et comfyui (commentés avec note).
Override du service langgraph_api :
  Variables d'env :
    GPU_PROFILE=api-only
    LLM_MODE_OVERRIDE=api
    IMAGE_GENERATION_MODE=api
    (FLUX.2 via Replicate API ou fal.ai comme fallback cloud)

Override du service pytorch_models :
  Supprime la configuration GPU
  Ajoute PYTORCH_DEVICE=cpu
  (les modèles PyTorch légers tournent en CPU  plus lent
   mais fonctionnel pour le classifieur et le scorer)

5. backend/core/gpu/model_swap_manager.py
NOUVEAU : gestionnaire de swap GPU pour le scénario single-gpu.

Ce composant est actif uniquement si GPU_PROFILE=single-gpu.

Classe ModelSwapManager avec :

État interne :
- current_occupant : Literal["vllm", "comfyui", "none"]
- swap_lock : Redis distributed lock (via redis-py RedLock)
- lock_ttl : int (depuis settings, défaut 120 secondes)
- swap_latency_ms : float (mesurée et exposée à Prometheus)

acquire_for_llm(requester: str, timeout: int = 30) → bool
  1. Tente d'acquérir le lock Redis "lidia:gpu:swap_lock"
  2. Si current_occupant == "comfyui" :
     Envoie POST http://comfyui:8188/api/unload_models
     Attend confirmation (polling 1s, max 30s)
     Si timeout → retourne False, log l'erreur
  3. current_occupant = "vllm"
  4. Retourne True
  Appelé par les workers LLM avant chaque appel vLLM
  en mode single-gpu

acquire_for_image(requester: str, timeout: int = 60) → bool
  1. Tente d'acquérir le lock Redis
  2. Si current_occupant == "vllm" :
     Envoie signal à vLLM pour libérer la VRAM :
     POST http://vllm:8080/v1/unload_model
     (ou redémarre le processus vLLM avec modèle minimal)
     Attend que nvidia-smi montre < 4GB utilisé
     Si timeout 60s → retourne False
  3. current_occupant = "comfyui"
  4. Retourne True
  Appelé par les workers image avant chaque génération

release(occupant: str) → None
  Si current_occupant == occupant :
    Libère le Redis lock
    current_occupant = "none"
    Log la durée d'occupation dans LangFuse

get_swap_status() → SwapStatus
  (current_occupant, lock_held_by, lock_expires_at,
   swaps_today: int, avg_swap_latency_ms: float,
   last_swap_at: datetime)

Exposition FastAPI interne :
POST /internal/gpu-swap/acquire-llm → bool
POST /internal/gpu-swap/acquire-image → bool
POST /internal/gpu-swap/release → None
GET  /internal/gpu-swap/status → SwapStatus
Ces routes sont accessibles uniquement depuis le réseau Docker
interne (pas exposées via nginx).

6. backend/tasks/workers/image_worker.py
MODIFICATION : intègre le ModelSwapManager dans le worker image.

Dans generate_visual_task() :

Au début de la tâche, avant d'appeler ComfyUI :
  Si GPU_PROFILE=single-gpu :
    acquired = await swap_manager.acquire_for_image(
      requester=f"image_worker_{task_id}"
    )
    Si not acquired :
      Retry la tâche dans 60 secondes (Celery retry)
      Log le swap timeout dans LangFuse

À la fin de la tâche, dans un bloc finally :
  Si GPU_PROFILE=single-gpu :
    swap_manager.release(f"image_worker_{task_id}")

Même pattern dans train_lora_task() :
  acquire_for_image avec timeout plus long (300 secondes)
  car l'entraînement peut nécessiter beaucoup de temps

7. backend/tasks/workers/llm_worker.py
MODIFICATION : intègre le ModelSwapManager dans le worker LLM.

Dans run_agent_task() et generate_content_task() :

Si GPU_PROFILE=single-gpu :
  Avant l'appel LLM :
    acquired = await swap_manager.acquire_for_llm(
      requester=f"llm_worker_{task_id}"
    )
    Si not acquired :
      Si LLM_MODE=hybrid : bascule sur API pour cette tâche
      Si LLM_MODE=local : retry dans 30 secondes

  Après l'appel LLM :
    swap_manager.release(f"llm_worker_{task_id}")

Note importante : en mode single-gpu, les appels LLM et image
ne peuvent pas être concurrents. La queue llm_inference a 
priorité sur image_generation (priority 9 vs 5 dans Celery).
Le ModelSwapManager respecte cette priorité via la queue Redis.

8. backend/config/settings.py
MODIFICATION : ajoute les variables de configuration GPU.

Ajoute :
- GPU_PROFILE : Literal["single-gpu", "dual-gpu", "api-only"]
  (défaut : "api-only"  safe par défaut)
- GPU_SWAP_LOCK_TTL : int (défaut : 120)
- GPU_SWAP_TIMEOUT_LLM : int (défaut : 30)
- GPU_SWAP_TIMEOUT_IMAGE : int (défaut : 60)
- IMAGE_GENERATION_MODE : Literal["local", "swap", "api"]
  local : ComfyUI sur GPU dédié (dual-gpu)
  swap : ComfyUI avec ModelSwapManager (single-gpu)
  api : Replicate/fal.ai cloud (api-only)
- REPLICATE_API_TOKEN : Optional[str]
  (pour le fallback cloud en mode api-only)

9. backend/core/monitoring/metrics_exporter.py
MODIFICATION : ajoute les métriques GPU swap dans Prometheus.

Ajoute :
lidia_gpu_swap_total (counter, par direction: llm→image/image→llm)
lidia_gpu_swap_latency_seconds (histogram)
lidia_gpu_swap_timeout_total (counter, par type: llm/image)
lidia_gpu_current_occupant (gauge: 0=none, 1=vllm, 2=comfyui)

Ces métriques apparaissent dans un nouveau panel "GPU Swap"
dans le dashboard Grafana operational_dashboard.json.

10. docs/deployment/gpu-profiles.md
NOUVEAU : documentation des trois profils GPU.

Section 1  Choisir son profil
  Tableau de décision :
  | Situation | Profil recommandé |
  |---|---|
  | Pas de GPU | api-only |
  | 1 GPU 24GB, usage modéré | single-gpu |
  | 1 GPU 24GB, usage intensif | single-gpu + LLM_MODE=hybrid |
  | 2 GPUs 24GB | dual-gpu |
  | Budget serré, images occasionnelles | api-only + Replicate |

Section 2  Lancement par profil
  Commandes exactes :
  Profil api-only :
    docker compose -f docker-compose.yml \
                   -f docker-compose.api-only.yml \
                   --profile api-only up -d

  Profil single-gpu :
    docker compose -f docker-compose.yml \
                   -f docker-compose.single-gpu.yml \
                   --profile single-gpu up -d

  Profil dual-gpu :
    docker compose -f docker-compose.yml \
                   -f docker-compose.dual-gpu.yml \
                   --profile dual-gpu up -d

Section 3  Vérification post-lancement
  Commandes nvidia-smi pour vérifier l'allocation VRAM
  par profil. Endpoints de health check à tester.
  Interprétation des métriques GPU swap dans Grafana.

Section 4  Comportement du swap (single-gpu)
  Explication du cycle de vie d'un swap LLM → Image → LLM.
  Latences attendues : 10-30 secondes par swap.
  Cas où le swap échoue et comportement du système 
  (fallback API automatique, retry Celery).

Section 5  Migration entre profils
  Procédure pour passer de single-gpu à dual-gpu
  sans perdre les données (volumes Docker préservés).
  Reconfiguration des variables d'environnement.

