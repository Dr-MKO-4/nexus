# Audit des écarts frontend ↔ backend  NEXUS AI

Date : 2026-09-18 (mis à jour le même jour  §2.5-2.8, implémentation des écarts §3.1/3.2/3.3 identifiés plus tôt)
Périmètre : `frontend/src/**` vs `backend/api/**` (+ ce que ces routes exposent réellement des workers Celery / LangGraph).
Méthode : lecture intégrale des 7 routers backend (`auth`, `campaigns`, `agents`, `hitl`, `content`, `analytics`, `settings`), comparaison champ par champ avec `frontend/src/services/api.ts` et `frontend/src/types/index.ts`, recherche exhaustive (`grep`) des appelants de chaque fonction/endpoint, et un test réel en navigateur headless (Playwright) pour détecter les bugs runtime invisibles à `tsc`/`eslint`.

---

## 1. Résumé exécutif

| Catégorie | Nombre | Statut |
|---|---|---|
| Bugs runtime réels (boucle infinie, RBAC absent, endpoint jamais appelé, etc.) | 3 majeurs | **Corrigés** |
| Endpoints campagnes/analytics jamais exposés côté UI (édition, archivage, historique, anomalies, détail de rapport) | 5 | **Corrigés** (nouvelle page Campagnes, sections ajoutées à Analytics) |
| Événements WebSocket écoutés côté client mais jamais émis côté serveur | 3 sur 9 | **Corrigés** (AGENT_STATUS, CAMPAIGN_UPDATE, BUDGET_UPDATE) ; `CONTENT_STREAM` reste non émis (aucun producteur SSE, hors périmètre) |
| Sections de `Settings.tsx` sans aucun backend | 2 sur 5 sous-sections (Marque client, Intégrations) | Assumé (maquette honnête  nécessitent une infra de stockage fichiers / de vrais identifiants OAuth2 non fabriquables) ; LLM et Utilisateurs corrigés |
| Limite structurelle non corrigeable côté frontend seul | 1 (compte admin) | Documentée |

---

## 2. Corrigé dans cette session

### 2.1 RBAC absent de l'interface (bug critique)

Le backend impose `require_role(ADMIN, MANAGER)` sur quasiment toute action de mutation :

| Endpoint | Rôles autorisés |
|---|---|
| `POST /campaigns`, `PATCH`, `DELETE`, `/pause`, `/resume` | ADMIN, MANAGER |
| `POST /hitl/{id}/approve\|reject\|modify` | ADMIN, MANAGER |
| `PATCH/POST /contents/{id}/*` | ADMIN, MANAGER |
| `POST /agents/{name}/trigger` | ADMIN, MANAGER |
| `GET /agents/{name}/logs` | ADMIN, MANAGER (même un GET) |

**Avant correctif** : un seul endroit dans tout le frontend vérifiait `user.role` (le label client de `Header.tsx`). Chaque bouton d'action (Approuver/Rejeter/Modifier, Publier/Archiver/Modifier, Pause/Reprendre, Déclencher, drag & drop du calendrier) était affiché à tout utilisateur connecté, y compris "viewer", qui recevait un 403 au clic. Pire : `useAgentLogs` était appelé sans condition pour chaque carte d'agent dans `AgentControl.tsx`  un viewer recevait un vrai 403, masqué par un faux message "Aucune décision enregistrée."

**Correctif** : nouveau hook `frontend/src/hooks/useCanMutate.ts` (`useCanMutate()`, `useCanViewAgentLogs()`), appliqué dans `HITLValidation.tsx`, `ContentManagement.tsx` (Bibliothèque, SEA, drag & drop du Calendrier) et `AgentControl.tsx`. `useAgentLogs()` accepte maintenant un 3ᵉ paramètre `enabled` pour ne plus exécuter la requête du tout pour un viewer.

### 2.2 Boucle de rendu infinie sur le Dashboard (bug critique)

Trouvé via un test réel en navigateur headless (Playwright), invisible à `tsc`/`eslint` :

```tsx
// AVANT  bug
const alerts = useAlertStore((s) => s.alerts.filter((a) => !a.read));
```

Un sélecteur Zustand qui recrée un nouveau tableau à chaque appel : Zustand compare par référence, voit "un changement" à chaque rendu, force un re-rendu, qui refait tourner le sélecteur, qui recrée un tableau différent → boucle infinie ("Maximum update depth exceeded", React error #185), reproduit tel quel dans un vrai navigateur.

**Correctif** (`frontend/src/pages/Dashboard.tsx`) :
```tsx
const rawAlerts = useAlertStore((s) => s.alerts);
const alerts = useMemo(() => rawAlerts.filter((a) => !a.read), [rawAlerts]);
```

### 2.3 Statut des providers LLM codé en dur

`Settings.tsx` affichait `{name: "Groq", online: true}` etc. codés en dur, sans aucun endpoint backend. Corrigé en ajoutant un vrai backend :

- **Nouveau** `backend/api/routes/settings.py` :
  - `GET /settings/llm/providers` → statut réel par provider (`configured` = clé API présente dans `settings`, PAS un ping réseau à chaque affichage de page).
  - `POST /settings/llm/providers/{name}/test` (ADMIN/MANAGER) → un VRAI appel `litellm.acompletion()` minimal (1 complétion, 5 tokens max) directement au provider testé (pas via le Router LiteLLM complet, qui ferait du fallback automatique  contre-productif pour un test isolé).
- Frontend : `getProviderStatus()`/`testProvider()` (`services/api.ts`), hook `useProviderStatus()`, `Settings.tsx` reconnecté aux vraies données + bouton "Tester" fonctionnel.
- Vérifié par exécution réelle (`py -c "..."`) : `configured=False` pour les 4 providers dans `.env.development` (clés vides  résultat honnête, pas fabriqué), 404 correct sur un nom de provider inconnu.

### 2.4 Nouvelle section "Nouvel objectif" (langage naturel → Orchestrateur)

`createCampaign()` existait dans `services/api.ts` depuis le début de Prompt 8.1 **sans aucun appelant**  trouvé lors de l'audit précédent. C'est pourtant exactement le point d'entrée demandé : `POST /campaigns` prend un champ `objective` en texte libre, transmis tel quel à `parse_objective_node` (Orchestrateur), qui le décompose lui-même via LLM.

**Ajouté** : `frontend/src/pages/NewObjective.tsx` (route `/objectifs`, nav Sidebar)  interface conversationnelle (fil de discussion) : l'objectif tapé apparaît comme message "envoyé", chaque changement de statut réel de la campagne (créée, en cours, en pause pour validation, terminée) apparaît comme message système, via `createCampaign()` puis polling `useCampaign()`. Aucun texte "assistant" n'est un message généré par un LLM conversationnel  l'Orchestrateur n'en produit pas, seul le statut réel est reflété.

### 2.5 Campagnes : modification, archivage et historique jamais exposés

`PATCH /campaigns/{id}`, `DELETE /campaigns/{id}` et `GET /campaigns/{id}/history` existaient déjà côté backend (Prompt 7.1) mais n'avaient **aucun appelant** côté frontend.

**Ajouté** : nouvelle page `frontend/src/pages/Campaigns.tsx` (route `/campagnes`, nav Sidebar) : liste des campagnes du client actif, modification (nom/objectif/budget) via une modale, archivage (soft-delete, confirmé), et un visualiseur d'historique affichant chaque checkpoint LangGraph (time-travel réel, `snapshot.next`/`snapshot.values`). Fonctions ajoutées à `services/api.ts` : `updateCampaign`, `archiveCampaign`, `getCampaignHistory`. Hooks : `useUpdateCampaign`, `useArchiveCampaign`, `useCampaignHistory`.

### 2.6 Anomalies et détail de rapport jamais exposés

`GET /analytics/anomalies` et `GET /analytics/reports/{id}` existaient côté backend sans aucun appelant frontend.

**Ajouté** (`Analytics.tsx`) : section "Anomalies détectées" (lit `AgentDecision` où `decision_type="anomaly_detected"`) et un lien cliquable sur chaque rapport listé, ouvrant son contenu complet (`WeeklyReport` ou autre) dans une modale. Fonctions ajoutées : `getAnomalies`, `getReportDetail`. Hooks : `useAnomalies`, `useReportDetail`.

### 2.7 3 événements WebSocket sur 9 jamais émis : corrigé pour les 3

`AGENT_STATUS`, `CAMPAIGN_UPDATE`, `BUDGET_UPDATE` n'avaient aucun point d'appel backend (vérifié par `grep -rn "broadcast_X" backend/` avant correctif). Corrigé à leur point d'appel le plus réaliste :

- **`AGENT_STATUS`** : émis dans les 5 nœuds d'agent réels (`run_seo_agent_node`/`run_sea_agent_node` dans `backend/core/graph/acquisition_cluster.py`, `run_content_agent_node`/`run_social_agent_node`/`run_email_agent_node` dans `backend/core/graph/engagement_cluster.py`)  `"running"` juste avant l'exécution du subgraph de l'agent, `"idle"` juste après un succès, `"error"` si le subgraph n'est pas encore implémenté (Prompts 5.1-5.5, replis existants). Chaque appel est défensif (`try/except`, un échec de broadcast ne casse jamais le run de l'agent).
- **`CAMPAIGN_UPDATE`**/**`BUDGET_UPDATE`** : émis ensemble par une nouvelle fonction `_notify_campaign_update()` (`backend/api/routes/campaigns.py`), appelée à chaque point où le statut/budget d'une campagne change réellement : fin de run/pause du graphe (`_persist_run_outcome`), `PATCH`, `DELETE` (archivage), `POST /pause`, `POST /resume`.

`CONTENT_STREAM` reste non émis (aucun producteur SSE identifié, limite déjà documentée à la création de `backend/api/sse/streams.py`  hors périmètre de ce correctif).

### 2.8 Gestion réelle des utilisateurs

`Settings.tsx` (section "Utilisateurs") gérait une liste en `useState` local, sans aucun appel réseau. `UserRepository`/`User` existaient déjà côté backend avec tous les champs nécessaires (email, hashed_password, role, client_id, is_active), sans qu'aucune route ne les expose.

**Ajouté** : nouveau `backend/api/routes/users.py` (`GET/POST /users`, `PATCH /users/{id}`, montés dans `main.py`), scopé par client comme `campaigns.py` (MANAGER restreint à son `client_id`, ADMIN sans restriction). L'invitation (`POST /users`) génère un mot de passe temporaire renvoyé une seule fois dans la réponse  **aucune infrastructure d'envoi d'email n'existe dans ce projet**, documenté honnêtement plutôt que fabriqué ; l'admin/manager doit le communiquer manuellement. `Settings.tsx` reconnecté aux vraies données (`useUsers`/`useCreateUser`/`useUpdateUser`), avec activation/désactivation de compte en un clic.

---

## 3. Écarts identifiés, statut

### 3.1 Endpoints campagnes/analytics jamais exposés côté UI — ✅ corrigé (§2.5, §2.6)

### 3.2 Événements WebSocket jamais émis par le backend — ✅ corrigé pour 3 sur 3 (§2.7)

`CONTENT_STREAM` reste non émis, voir §2.7.

### 3.3 `Settings.tsx` : sous-sections sans backend

- **LLM & Modèles** : "Statut des providers" ✅ réel (§2.3), reste (mode LLM, seuils de routage) local uniquement.
- **Agents & Automatisation** : 100% local (seuils HITL, autonomie, tâches Celery Beat  les noms de tâches affichés sont réels, mais les toggles ne persistent rien).
- **Marque client** : 100% local, aucun upload de fichier possible — nécessiterait une route multipart + un stockage de fichiers (S3/disque), infrastructure absente de ce backend. Non fabriqué.
- **Intégrations** : 100% local, aucun flux OAuth2 réel — nécessiterait de vrais identifiants applicatifs (client_id/secret) par intégration (Google Ads, Meta, etc.), impossibles à fabriquer sans decision produit/API keys réelles. Non fabriqué.
- **Utilisateurs** : ✅ réel (§2.8).

### 3.4 Limite structurelle : les comptes admin ne peuvent rien afficher

`User.client_id` est `NULL` pour un compte ADMIN (par design, `db/models/users.py`). `useActiveClientId()` retourne donc `null` pour un admin, et **toutes** les pages scopées par client (Dashboard, Contenus, Analytics, Nouvel objectif) affichent "Aucun client actif". Il n'existe aucun endpoint "lister les clients" dans ce backend (`ClientRepository` n'a que `get_by_name`)  impossible à corriger côté frontend seul. Nécessiterait `GET /clients` côté backend + un sélecteur de client dans `Header.tsx`.

---

## 4. Fichiers modifiés dans cette session

- `backend/api/routes/settings.py` (nouveau)
- `backend/api/routes/users.py` (nouveau)
- `backend/api/main.py` (montage des routers settings + users)
- `backend/api/routes/campaigns.py` (`_notify_campaign_update`, appelé depuis `_persist_run_outcome`/`update`/`archive`/`pause`/`resume`)
- `backend/core/graph/acquisition_cluster.py` (`AGENT_STATUS` pour seo/sea)
- `backend/core/graph/engagement_cluster.py` (`AGENT_STATUS` pour content/social/email)
- `backend/db/repositories/user_repository.py` (`get_by_client`)
- `frontend/src/hooks/useCanMutate.ts` (nouveau)
- `frontend/src/hooks/useProviderStatus.ts` (nouveau)
- `frontend/src/hooks/useCampaignMutations.ts` (nouveau : `useCampaignHistory`, `useUpdateCampaign`, `useArchiveCampaign`)
- `frontend/src/hooks/useAnomalies.ts` (nouveau)
- `frontend/src/hooks/useReportDetail.ts` (nouveau)
- `frontend/src/hooks/useUsers.ts` (nouveau)
- `frontend/src/hooks/useAgentLogs.ts` (paramètre `enabled`)
- `frontend/src/hooks/useCampaign.ts` (paramètre `options` pour le polling)
- `frontend/src/hooks/index.ts` (exports)
- `frontend/src/services/api.ts` (`getProviderStatus`, `testProvider`, `updateCampaign`, `archiveCampaign`, `getCampaignHistory`, `getAnomalies`, `getReportDetail`, `getUsers`, `createUser`, `updateUser`)
- `frontend/src/types/index.ts` (`Anomaly`, `CampaignHistorySnapshot`)
- `frontend/src/pages/Dashboard.tsx` (fix boucle infinie)
- `frontend/src/pages/HITLValidation.tsx` (RBAC)
- `frontend/src/pages/ContentManagement.tsx` (RBAC, y compris drag & drop)
- `frontend/src/pages/AgentControl.tsx` (RBAC)
- `frontend/src/pages/Settings.tsx` (statut providers réel, gestion utilisateurs réelle)
- `frontend/src/pages/NewObjective.tsx` (nouveau, puis redesigné en interface conversationnelle)
- `frontend/src/pages/Campaigns.tsx` (nouveau : liste, édition, archivage, historique)
- `frontend/src/pages/Analytics.tsx` (sections Anomalies + détail de rapport, libellé "Analyses")
- `frontend/src/App.tsx` (routes `/objectifs`, `/campagnes`)
- `frontend/src/components/layout/Sidebar.tsx` (nav "Nouvel objectif"/"Campagnes"/"Analyses", logo)
- `frontend/src/components/layout/Header.tsx` (titres de page)
- `frontend/index.html` (favicon réel)
