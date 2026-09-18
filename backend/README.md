# Backend NEXUS AI

Service backend de la plateforme multi-agents NEXUS AI.

## Contenu

- `agents/`  Agents IA spécialisés (orchestrateur, SEO, SEA, contenu, social, email, analytics, reporting, créatif)
- `core/`  Cœur d'orchestration : état, routage, mémoire, graphe d'exécution
- `llm/`  Abstraction d'accès aux modèles de langage (gateway, fournisseurs, routage)
- `pytorch_models/`  Modèles PyTorch internes (classification, embeddings, scoring, anomalies)
- `api/`  API exposée aux clients (routes REST, WebSocket, SSE)
- `tasks/`  Traitement asynchrone (files d'attente, workers)
- `tools/`  Outils métier utilisés par les agents pour interagir avec les plateformes externes
- `db/`  Migrations, modèles ORM et repositories
- `config/`  Configuration applicative par environnement

## Responsabilités

Orchestrer les agents IA, exposer une API pour le frontend, exécuter les tâches longues en arrière-plan et persister les données métier.
