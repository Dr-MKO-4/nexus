# Frontend NEXUS AI

Application web frontend de la plateforme NEXUS AI.

## Contenu

- `src/components/`  Composants UI réutilisables
- `src/pages/`  Pages de l'application
- `src/hooks/`  Hooks React personnalisés
- `src/store/`  Gestion de l'état global
- `src/services/`  Services d'accès à l'API backend
- `src/types/`  Types et interfaces TypeScript partagés
- `public/`  Fichiers statiques

## Responsabilités

Fournir l'interface utilisateur permettant de piloter les agents IA, visualiser les campagnes et consulter les rapports générés par le backend.

## Branche `demo` : démo sans backend

`npm run build:demo` (fichier `.env.demo`, `VITE_DEMO=true`) produit une version qui tourne entièrement dans le navigateur :
l'adaptateur axios, le service WebSocket et le flux SSE sont remplacés par une simulation en mémoire (`src/demo/`).
Clients, campagnes, contenus et chiffres sont fictifs ; le graphe de l'orchestrateur, les clusters d'agents, les noms de
tâches Celery et la règle de validation humaine (écart > 50 % sur un KPI cible) reprennent le code du backend. Aucun LLM
n'est appelé.
