**NEXUS AI**

_Votre bureau d'intelligence artificielle_

**Architecture Technique**

Plateforme d'Agents IA pour le Marketing Digital

| **Version**  | 1.0  2026               |
| ------------ | ------------------------ |
| **Émetteur** | Nexus                    |
| **Statut**   | Document confidentiel    |
| **Usage**    | Équipes techniques NEXUS AI |

_<www.nexus.com> · contact@nexus.com_

# **Couche 1  Orchestration : LangGraph**

LangGraph est le framework retenu pour orchestrer les agents IA de la plateforme. Son architecture en graphe d'état offre la capacité de rendre la progression visible en temps réel. Un agent qui met 30 secondes à répondre se ressent très différemment quand on le voit travailler.

## **Le contrôle humain (HITL)**

À l'intérieur d'un nœud, on insère un checkpoint. Quand l'exécution du graphe atteint ce checkpoint désigné, LangGraph met le workflow en pause et présente les informations pertinentes à l'humain. Pour le déploiement en production, on utilise un checkpointer adossé à une vraie base de données comme PostgresSaver ou SqliteSaver. LangGraph abstrait cela : passer du développement à la production ne nécessite de changer qu'une seule ligne de code, le reste de la logique du graphe restant inchangé.

## **La mémoire**

La couche de persistence de LangGraph donne aux agents une mémoire court-terme via les checkpointers et une mémoire long-terme via les stores. Les checkpointers persistent l'état du thread sous forme de checkpoints, utilisables pour la continuité des conversations, les workflows human-in-the-loop, le time-travel et la tolérance aux pannes. Les stores persistent des données définies par l'application en dehors de l'état du graphe.

## **Les patterns d'orchestration et leurs compromis**

### **Le pattern Supervisor**

Le pattern Supervisor est le plus courant en entreprise. Un nœud classifie l'intention et route vers des agents spécialistes. C'est le pattern derrière langgraph-supervisor et le déploiement enterprise le plus courant. Le prompt du supervisor devient un composant central surchargé si l'on y entasse un trop grand nombre d'intentions dans un seul routeur. Pour notre système, la réponse est claire : l'orchestrateur ne gère que trois clusters, pas chaque agent individuellement.

### **Le pattern Orchestrator-Worker avec Send API**

Le pattern Orchestrator-Worker avec Send API est ce qui rend le système réellement parallèle. Le Send API permet de créer dynamiquement des nœuds workers et de leur envoyer des inputs spécifiques. Chaque worker a son propre état, et tous les outputs des workers sont écrits dans une clé d'état partagée accessible à l'orchestrateur. Cela donne à l'orchestrateur accès à tous les outputs des workers et lui permet de les synthétiser en un output final.

### **Le pattern Generator-Evaluator**

Le pattern Generator-Evaluator constitue la boucle d'optimisation native du système. Un générateur produit un output, un évaluateur le score selon des critères, une arête conditionnelle boucle en arrière ou sort. Ce mécanisme est courant pour la génération de code, les drafts de conformité, et le contenu marketing. La boucle est native à LangGraph  aucun prompt correctif supplémentaire n'est nécessaire.

### **Les Subgraphs**

Les Subgraphs sont la clé de la modularité. Un seul agent avec beaucoup d'outils atteint rapidement un plafond. À mesure qu'on ajoute des outils, le LLM devient moins fiable pour choisir le bon, et le system prompt devient ingérable. Différentes tâches requièrent différentes configurations de modèle. Les systèmes multi-agents résolvent cela en décomposant des workflows complexes en agents spécialisés, chacun focalisé sur un domaine étroit, coordonnés par un superviseur.

## **Persistence : la progression selon l'environnement**

La progression est claire selon l'environnement : MemorySaver pour le développement uniquement (reset au redémarrage), SqliteSaver pour les tests locaux avec persistence entre redémarrages, et PostgresSaver pour la production avec scaling horizontal et crash recovery.

LangGraph sérialise l'état complet du graphe après chaque exécution de nœud. En production, cet état est persisté dans un store externe  PostgreSQL, Redis, ou un backend custom  pour que l'exécution du graphe puisse reprendre après une interruption, revenir à n'importe quel état précédent, ou brancher vers des timelines parallèles pour l'évaluation. Le checkpointing ajoute un petit write par nœud par exécution, ce qui est négligeable comparé à la latence d'inférence LLM.

| **Environnement** | **Outil**     | **Usage**                                                          |
| ----------------- | ------------- | ------------------------------------------------------------------ |
| **Développement** | MemorySaver   | Reset au redémarrage  uniquement pour le développement local      |
| **Tests locaux**  | SqliteSaver   | Persistence entre redémarrages  adapté aux environnements de test |
| **Production**    | PostgresSaver | Scaling horizontal et crash recovery  obligatoire en production   |

## **Observabilité avec LangFuse**

LangFuse a été retenu dans notre stack plutôt que LangSmith pour une raison précise : LangFuse est entièrement self-hostable et open source, ce qui correspond à notre contrainte de souveraineté des données.

La vue graphe d'agent dans LangFuse transforme une trace en image de ce que l'agent a fait : des nœuds pour les étapes, des arêtes pour la façon dont l'exécution s'est déplacée entre eux. LangFuse infère le graphe automatiquement à partir des timings et de l'imbrication des observations, et cela apparaît automatiquement pour l'intégration LangGraph.

Depuis juillet 2026, la vue graphe propose deux modes : Aggregated, qui montre la forme globale de l'agent (retrieve_docs 3/3 signifie que cette étape a tourné trois fois, et les boucles se dessinent comme des cycles), et Expanded, qui montre l'exécution pas à pas avec chaque appel comme son propre nœud et les boucles déroulées dans l'ordre d'exécution.

Pour notre plateforme, LangFuse nous donnera en production la capacité de détecter immédiatement si un agent tourne en boucle, consomme trop de tokens, ou prend trop de temps sur une étape spécifique  directement depuis notre infrastructure self-hosted.

## **Tolérance aux pannes en production**

La tolérance aux pannes est un pilier du déploiement en production. LangGraph supporte les retries automatiques, les timeouts par nœud, et la capacité de mettre en pause et reprendre des workflows à des nœuds spécifiques. Ces fonctionnalités permettent une récupération d'erreur custom, comme escalader des problèmes ou réassigner des tâches, garantissant la fiabilité même lors de pannes inattendues.

Le décorateur @retry, la classe TimeoutPolicy, et les nœuds ErrorHandler représentent la réponse comprehensive de LangGraph à ce défi, construite sur l'architecture d'agents résilients existante du framework tout en adressant les réalités opérationnelles des workloads agentiques de 2026.

## **Les limites réelles à connaître avant de construire**

Aucun framework n'est parfait. Les équipes qui ont LangGraph en production depuis plus d'un an remontent des points de friction précis qu'il faut anticiper.

### **Le partage d'état cross-graphe**

Le partage d'état cross-graphe est encore maladroit. Les équipes qui ont construit des systèmes où un graphe de recherche et un graphe d'exécution partagent un état ont constaté que LangGraph n'a pas de support first-class pour cela. La solution qui fonctionne en pratique : des tables PostgreSQL partagées avec des handoffs explicites à la frontière. Des race conditions apparaissent quand les deux graphes mettent à jour l'état partagé simultanément. Pour notre système, la réponse est dans l'architecture en subgraphs avec un état central géré uniquement par l'orchestrateur  les agents spécialisés ne s'écrivent pas dessus directement.

### **Les tests du graphe complet**

Les tests du graphe complet sont fastidieux. Les nœuds individuels sont juste des fonctions, donc les tester unitairement est facile. Tester le graphe complet nécessite de mocker le modèle et les appels d'outils de manière cohérente sur plusieurs étapes. La bonne pratique : des tests unitaires au niveau des nœuds et deux ou trois tests d'intégration qui font tourner le graphe complet contre des fixtures. Il est déconseillé de tenter de couvrir chaque chemin de branchement dans la suite d'intégration.

### **Le fanout parallèle sans validation**

Le fanout parallèle sans validation est dangereux. LangGraph supporte l'exécution parallèle via Send(). Quand cinq nœuds tournent en parallèle et qu'un échoue silencieusement  retourne un dict vide, dépasse le contexte, atteint une rate limit  l'état fusionné est incomplet. Le nœud downstream voit des données partielles sans indication de ce qui manque. Il faut ajouter un nœud de validation après tout fanout parallèle qui vérifie que les champs requis sont présents avant de continuer.

### **La courbe d'apprentissage**

La courbe d'apprentissage est réelle. La flexibilité de LangGraph s'accompagne de défis : une courbe d'apprentissage prononcée, une complexité de débogage, et des besoins d'infrastructure significatifs pour le déploiement en production. La conception de workflows fiables et le débogage d'interactions distribuées peuvent être très complexes.

## **Ce que cela implique concrètement pour notre architecture**

En synthèse de tout ce qui précède, voici les décisions d'architecture que ces recherches confirment ou ajustent pour notre système :

**Sur l'orchestration :** le pattern Supervisor à trois clusters (Acquisition, Engagement, Mesure) est le bon niveau de granularité. Un orchestrateur qui gère sept agents directement deviendrait le composant central surchargé que les équipes en production dénoncent.

**Sur la persistence :** PostgresSaver dès la première version de production, pas de MemorySaver qui disparaît au redémarrage. L'état d'une campagne qui tourne depuis trois jours ne peut pas être perdu.

**Sur la validation parallèle :** chaque fanout vers plusieurs agents doit être suivi d'un nœud de validation qui vérifie que tous les résultats attendus sont bien présents avant de continuer.

**Sur les boucles :** toutes les boucles d'optimisation (Content → Évaluateur SEO → Content) doivent avoir un compteur d'itérations et un plafond explicite. Une boucle infinie en production est un coût LLM qui explose.

**Sur l'observabilité :** LangFuse se connecte à LangGraph dès le début, pas après coup. Les équipes qui l'ajoutent en rattrapage passent deux à trois fois plus de temps à déboguer leurs premiers incidents de production.

# **Couche 2  Modèles LLM & Infrastructure d'inférence**

## **Les modèles LLM retenus**

Trois modèles sont retenus. Chacun a un rôle précis dans le système.

| **Modèle**        | **Taille** | **Licence**     | **Rôle dans le système**                             |
| ----------------- | ---------- | --------------- | ---------------------------------------------------- |
| **Llama 3.3 70B** | 70B        | Llama Community | Modèle principal  tâches complexes                  |
| **Qwen3.5 72B**   | 72B        | Apache 2.0      | Modèle multilingue  contenu français et multilingue |
| **Mistral 7B**    | 7B         | Apache 2.0      | Modèle léger  tâches simples et rapides             |

Justification du choix de ces trois modèles : Llama 3.3 70B est le modèle dense le plus testé en production en 2026, il tient sur un seul GPU haut de gamme. Qwen3.5 est le seul modèle open source avec un support natif du français en qualité production parmi les 29 langues qu'il couvre. Mistral 7B est le plus permissif commercialement (Apache 2.0 sans restriction) et le plus efficace sur les tâches légères.

## **Quel modèle pour quelle tâche dans notre système**

| **Agent**           | **Tâche**                                         | **Modèle retenu** | **Pourquoi**                                   |
| ------------------- | ------------------------------------------------- | ----------------- | ---------------------------------------------- |
| **Orchestrateur**   | Planification, arbitrage, décision stratégique    | Llama 3.3 70B     | Raisonnement complexe, fiabilité en production |
| **Agent SEO**       | Analyse mots-clés, audit technique, briefs        | Mistral 7B        | Extraction, classification, tâche structurée   |
| **Agent SEA**       | Génération d'annonces, analyse enchères           | Mistral 7B        | Tâche courte et structurée                     |
| **Agent Content**   | Génération articles, posts, emails, landing pages | Qwen3.5 72B       | Contenu long, qualité française                |
| **Agent Social**    | Analyse sentiment, détection tendances            | Mistral 7B        | Classification rapide                          |
| **Agent Email**     | Segmentation, rédaction séquences                 | Qwen3.5 72B       | Contenu personnalisé, contexte long            |
| **Agent Analytics** | Analyse cross-canal, détection anomalies          | Llama 3.3 70B     | Raisonnement analytique multi-données          |
| **Agent Reporting** | Synthèse, rapports lisibles                       | Qwen3.5 72B       | Rédaction qualitative en français              |

## **Comment les trois modes se répartissent**

### **LLM_MODE=local**

Tout tourne sur l'infrastructure propre au client. Aucun token ne sort vers l'extérieur.

| **Composant**       | **Outil**                                | **Usage**                           |
| ------------------- | ---------------------------------------- | ----------------------------------- |
| **Développement**   | Ollama                                   | Prototypage, tests locaux agents    |
| **Production**      | vLLM                                     | Déploiement avec charge concurrente |
| **Modèles chargés** | Llama 3.3 70B + Qwen3.5 72B + Mistral 7B | Selon la tâche                      |

### **LLM_MODE=api**

Aucun GPU nécessaire. Tout passe par des fournisseurs externes.

| **Fournisseur**  | **Modèle servi**             | **Rôle**                            | **Coût approximatif** |
| ---------------- | ---------------------------- | ----------------------------------- | --------------------- |
| **Groq**         | Llama 3.3 70B, Mistral       | Primary  ultra rapide (500+ tok/s) | 0,59 \$/M tokens      |
| **Together AI**  | Llama 3.3 70B, Qwen, Mistral | Fallback si Groq indisponible       | Compétitif            |
| **Mistral API**  | Mistral Large 2              | Clients RGPD / données européennes  | Variable              |
| **Fireworks AI** | Llama, Qwen, DeepSeek        | Troisième fallback                  | Compétitif            |

### **LLM_MODE=hybrid**

Le routeur décide automatiquement selon quatre critères.

| **Critère**                 | **Seuil**                    | **Action du routeur**                           |
| --------------------------- | ---------------------------- | ----------------------------------------------- |
| **Complexité de la tâche**  | Simple vs complexe           | Simple → Mistral 7B local. Complexe → Llama 70B |
| **Sensibilité des données** | Données clients, financières | Forcé en local, jamais vers API externe         |
| **Charge GPU locale**       | \> 80 % d'utilisation        | Débordement automatique vers API                |
| **Coût journalier API**     | Seuil configurable en \$     | Seuil dépassé → bascule sur local               |

## **Le gateway LiteLLM au centre des trois modes**

LiteLLM est le composant qui rend les trois modes transparents pour le reste du système. LangGraph n'appelle qu'un seul endpoint. LiteLLM décide où envoyer la requête selon la configuration du mode actif.

| **Mode actif** | **LiteLLM route vers**                              |
| -------------- | --------------------------------------------------- |
| **local**      | vLLM local (port interne Docker)                    |
| **api**        | Groq → fallback Together AI → fallback Fireworks    |
| **hybrid**     | Routeur de complexité → local ou API selon critères |

Le passage d'un mode à l'autre ne nécessite de changer qu'une variable d'environnement. Le code applicatif et les agents LangGraph ne changent pas.

## **L'économie des trois modes**

| **Mode**           | **Coût fixe**                               | **Coût variable**                    | **Recommandé pour**                    |
| ------------------ | ------------------------------------------- | ------------------------------------ | -------------------------------------- |
| **local (Ollama)** | Zéro                                        | Zéro                                 | Développement uniquement               |
| **local (vLLM)**   | GPU : 0,35 à 2,89 \$/heure (RunPod/Vast.ai) | Électricité + maintenance            | \> 10 M tokens/jour, données sensibles |
| **api**            | Zéro                                        | 0,05 à 0,79 \$/M tokens selon modèle | Démarrage, faible volume               |
| **hybrid**         | GPU partiel                                 | API pour les pics                    | Volume croissant, budget maîtrisé      |

Le break-even entre self-hosting et API se situe autour de 5 à 10 millions de tokens par mois pour un modèle de classe 70B. En dessous, l'API est plus économique. Au-dessus, le self-hosting amortit le GPU rapidement.

## **Pourquoi c'est la couche la plus stratégique**

C'est la seule couche qui touche simultanément à deux enjeux critiques : la qualité des outputs marketing que le système produit, et le coût d'exploitation qui détermine si le produit est économiquement viable à l'échelle. En 2026, les modèles open source ont définitivement fermé l'écart avec les modèles propriétaires. La décision ne porte plus sur la performance  elle porte sur les économies, le contrôle et la capacité opérationnelle. L'architecture à trois modes est précisément la réponse correcte à cette réalité.

## **Mode LOCAL  Option A : Ollama vs vLLM**

Ces deux outils ne sont pas interchangeables. Ils sont construits pour des objectifs différents. Ollama optimise pour la simplicité : faire tourner un modèle aussi vite que possible avec un effort minimal. vLLM optimise pour l'efficacité : traiter autant de requêtes par GPU que possible pour une opération à l'échelle.

### **Ollama**

Ollama est l'outil qui a rendu les LLMs locaux accessibles. Une commande suffit pour lancer un modèle. Il tourne même sans GPU grâce aux kernels AVX-512 optimisés de llama.cpp. C'est l'outil de développement par excellence : cold start en 3 secondes, zéro friction pour prototyper. Sa limite est structurelle : sous charge concurrente, à 20 utilisateurs simultanés, Ollama met 19 d'entre eux en attente. Sa latence P99 dégrade à 673 ms sous charge, contre 80 ms pour vLLM dans les mêmes conditions. Un seul utilisateur lent bloque tous ceux qui suivent.

### **vLLM**

vLLM est construit pour la production dès le départ. Son architecture repose sur deux innovations majeures. La première est le PagedAttention : gestion du cache KV en pages mémoire non contiguës, similaire à la gestion de mémoire virtuelle d'un OS. Cela lui permet de gérer beaucoup plus de séquences concurrentes avant de saturer la VRAM. Sur un H100 80 GB servant Llama 3.1 8B, vLLM peut sustenir 180+ requêtes FP16 concurrentes avant OOM là où Ollama sature autour de 40. La seconde est le batching continu : vLLM traite les 20 requêtes simultanées dans le même forward pass au lieu de les mettre en file. Le résultat en production est sans appel : la latence P99 de vLLM reste à 80 ms sous charge là où Ollama dégrade à 673 ms  un ordre de grandeur d'écart.

Décision pour notre système : Ollama pour le développement local des agents. vLLM pour le déploiement production dès qu'on dépasse une poignée d'utilisateurs simultanés ou qu'on tourne plusieurs agents en parallèle. Les deux exposent une API REST compatible OpenAI, donc le code ne change pas entre les deux environnements.

## **Le choix des modèles open source en 2026**

Le paysage a beaucoup évolué en 2025-2026. Les modèles open source ont fermé l'écart avec les modèles propriétaires sur la plupart des tâches marketing et sont désormais à parité ou meilleurs sur plusieurs benchmarks.

### **Llama 3.3 70B**

Llama 3.3 70B reste le modèle dense le plus testé en production et le plus finement tuné par l'écosystème. Il est disponible sous la Llama Community License (gratuit jusqu'à 700 M MAU). Il tient sur un seul GPU haut de gamme sans infrastructure MoE. C'est notre ancre : le modèle par défaut pour les tâches complexes (génération de contenu long, raisonnement de l'orchestrateur) en mode local.

### **Qwen 3.5**

Qwen 3.5 (famille Alibaba) est devenu incontournable depuis mars 2026. Sa force principale pour notre cas d'usage : il supporte nativement 29 langues dont le français, l'arabe, l'allemand. Qwen 3.5-72B surpasse Llama 3.3 70B sur plusieurs benchmarks de génération multilingue. Le Qwen 3.8-27B tient sur 24 GB de VRAM en Q4, ce qui le rend très attractif sur des GPUs accessibles. Pour un système marketing déployé en Afrique francophone ou en contexte multilingue, Qwen est notre modèle secondaire privilégié.

### **Mistral 7B**

Mistral (entreprise française, Apache 2.0) garde sa pertinence sur deux aspects : sa licence Apache 2.0 est la plus permissive du marché (aucune restriction commerciale), et ses modèles légers comme Mistral 7B sont très efficaces sur les tâches simples de classification et de routage. C'est notre modèle pour les tâches légères en mode local.

### **DeepSeek V3.2**

DeepSeek V3.2 mérite attention pour les tâches de raisonnement complexe : son architecture MoE active seulement 37 B paramètres sur 671 B totaux, ce qui lui donne un ratio performance/coût compute exceptionnel. À considérer pour les décisions stratégiques de l'orchestrateur.

## **Tableau de mapping modèles / tâches agents**

| **Tâche**                               | **Modèle recommandé**          | **Justification**            |
| --------------------------------------- | ------------------------------ | ---------------------------- |
| **Décision orchestrateur**              | Llama 3.3 70B ou DeepSeek V3.2 | Raisonnement complexe        |
| **Génération contenu long**             | Llama 3.3 70B ou Qwen 3.5 72B  | Qualité + cohérence          |
| **Contenu multilingue / français**      | Qwen 3.5                       | Support natif 29 langues     |
| **Classification, routage**             | Mistral 7B                     | Rapide, léger, efficace      |
| **Analyse SEO, résumé**                 | Mistral 7B ou Qwen 3.5 9B      | Tâche simple, faible latence |
| **Raisonnement analytique (Analytics)** | DeepSeek V3.2                  | Chain-of-thought natif       |

## **Mode API  Option B : les fournisseurs**

L'écosystème des fournisseurs d'APIs open source a émergé comme alternative réelle au self-hosting GPU. Groq, Together AI, Mistral API, et Fireworks AI servent les mêmes modèles open source à 50-90 % moins cher que les APIs propriétaires comme OpenAI ou Anthropic.

### **Groq**

Groq se différencie par son silicon custom : le LPU (Language Processing Unit), conçu spécifiquement pour l'inférence LLM. Résultat : 500+ tokens par seconde sur Llama 3.1 8B, 5 à 10 fois plus rapide que du GPU standard. Pricing en juin 2026 : Llama 3.1 8B Instant à 0,05 \$/M tokens en entrée, Llama 3.3 70B à 0,59 \$/M tokens en entrée.

_Point de vigilance : fin 2025, Nvidia a racheté la technologie LPU de Groq et embauché son CEO fondateur. Groq Cloud continue d'opérer mais la direction produit à long terme est observée avec prudence par la communauté des développeurs. Pour des systèmes en production, ne jamais architecturer une dépendance exclusive à Groq._

### **Together AI**

Together AI offre la sélection de modèles la plus large pour expérimenter avec des modèles open source à des prix compétitifs. C'est le fournisseur de backup naturel si Groq pose des problèmes de disponibilité. Il supporte Llama, Mistral, Qwen, DeepSeek et des dizaines d'autres.

### **Mistral API**

Mistral API est notre choix pour les contextes RGPD stricts. Entreprise française, serveurs européens, conformité native. Mistral Large 2 à 123 B paramètres en 80+ langues est disponible via leur API. Pour les clients institutionnels ou les marchés africains francophones où la souveraineté des données vers des serveurs européens est un argument commercial, Mistral API est le fournisseur par défaut du mode B.

### **Fireworks AI**

Fireworks AI est la valeur montante : tarification compétitive, bonne disponibilité, supporte les mêmes modèles que Together AI. À utiliser comme troisième option de failover.

La bonne pratique recommandée par les équipes en production : configurer un LLM gateway comme LiteLLM avec Groq en primary et Together AI ou Fireworks AI en backup. Si un provider supprime un modèle ou subit une panne, le failover est automatique sans toucher au code applicatif.

## **Mode HYBRID  Le routeur intelligent**

C'est la pièce centrale qui rend l'architecture viable économiquement à long terme. Le routeur est un composant à part entière dans LangGraph, un nœud qui précède chaque appel LLM et décide du fournisseur.

Le routage par complexité est l'une des manières les plus efficaces de réduire le coût LLM sur des workloads mixtes. Les systèmes de routage hybrides  qui envoient les requêtes basiques vers des modèles plus légers et réservent les modèles frontier pour le raisonnement complexe  atteignent des réductions de 37 à 46 % de l'utilisation LLM globale avec des réponses 32 à 38 % plus rapides sur les requêtes simples.

Un classifieur de 100 lignes avec des heuristiques  nombre de tokens, présence de code, expressions régulières pour des patterns de question  donne 80 % de la valeur. Le routeur n'a pas besoin d'être sophistiqué pour être efficace.

Les stratégies de routage forment une échelle de complexité croissante : règles statiques, splits pondérés, routage par latence, routage par coût, routage sémantique, et cascades de modèles. Le routage statique ou par règles  router par endpoint, en-tête ou tag de tâche que l'appelant définit  est sub-milliseconde, déterministe et trivial à déboguer.

La latence ajoutée par le routeur est réelle mais petite par rapport à l'inférence. Un routage basé sur des règles ajoute moins d'1 ms. Un routage basé sur des embeddings ajoute environ 5 ms. Un routage sémantique ou par classifieur ML lourd ajoute 50 à 100 ms. En regard des temps de réponse LLM typiques de 500 à 2 000 ms, la stratégie de routage la plus coûteuse reste un pourcentage à un seul chiffre du temps total.

### **Les critères de routage pour notre système**

**Complexité de la tâche :** génération de contenu long, raisonnement stratégique de l'orchestrateur, analyse multi-canaux → modèle fort. Classification, extraction, résumé court, routage interne → modèle léger.

**Sensibilité des données :** données clients, informations financières, drafts stratégiques → mode local uniquement, jamais d'API externe.

**Charge GPU locale :** si le serveur tourne à plus de 80 % de charge, déversement automatique sur l'API.

**Seuil de coût journalier :** si la dépense API dépasse le seuil configuré, bascule sur le local pour absorber la charge restante.

## **Structure des variables d'environnement**

<div class="joplin-table-wrapper"><table><tbody><tr><th><pre><code>LLM_MODE=local | api | hybrid</code></pre><p></p><pre><code># Mode local
LOCAL_INFERENCE_ENGINE=ollama | vllm
LOCAL_DEFAULT_MODEL=llama3.3:70b
LOCAL_FAST_MODEL=mistral:7b</code></pre><p></p><pre><code># Mode API
API_PRIMARY_PROVIDER=groq | together | mistral
API_FALLBACK_PROVIDER=together | fireworks
API_DEFAULT_MODEL=llama-3.3-70b-versatile
API_FAST_MODEL=llama-3.1-8b-instant</code></pre><p></p><pre><code># Mode Hybrid
HYBRID_COST_DAILY_LIMIT_USD=50
HYBRID_GPU_LOAD_THRESHOLD=0.8
HYBRID_SENSITIVE_TASKS=seo_audit,financial_report,client_data</code></pre></th></tr></tbody></table></div>

## **Ce que cela donne en pratique**

**Sans GPU (LLM_MODE=api) :** tout passe par Groq et Together AI, zéro infrastructure à gérer.

**Avec GPU dédié (LLM_MODE=local) :** tout tourne en self-hosted, coût d'exploitation minimal sur le long terme.

**En production mature (LLM_MODE=hybrid) :** les tâches légères absorbées localement, les pics de charge débordent sur l'API, les données sensibles restent sur site.

## **L'économie du self-hosting : les chiffres**

Le prix de location GPU est le plancher, pas le plafond. Chaque déploiement LLM self-hosted a des coûts supplémentaires que les équipes sous-estiment systématiquement. Il faut configurer le serveur d'inférence, gérer le chargement des modèles, ajuster les batch sizes, gérer les drivers GPU, gérer la compatibilité CUDA, et maintenir le tout en fonctionnement. Ce n'est pas une configuration ponctuelle  c'est de la maintenance continue. Conservativement, un déploiement LLM self-hosted nécessite 10 à 20 heures par mois de temps d'ingénierie pour la maintenance.

Le self-hosting atteint le break-even à 5 à 10 millions de tokens par mois pour les modèles premium. La plupart des équipes devraient commencer avec des APIs et migrer vers l'hybride à l'échelle.

Pour la location GPU : RunPod à environ 0,34 à 0,69 \$/heure pour une RTX 4090 est la valeur équilibrée par défaut. Vast.ai en spot est le moins cher pour les jobs interruptibles. Lambda Labs est le choix quand une équipe a besoin d'une garantie de disponibilité de 99,9 %.

## **Synthèse : le mapping complet des trois modes**

| **Situation**                         | **Mode recommandé**      | **Justification**                            |
| ------------------------------------- | ------------------------ | -------------------------------------------- |
| **Développement, prototypage**        | local (Ollama)           | Zéro coût, zéro latence réseau               |
| **Déploiement sans GPU**              | api (Groq + Together AI) | Pas d'infrastructure, démarrage immédiat     |
| **Client avec GPU dédié**             | local (vLLM)             | Coût fixe, données sur site                  |
| **Client institutionnel RGPD**        | api (Mistral API)        | Serveurs européens, conformité native        |
| **Client données sensibles**          | local (vLLM)             | Aucun transit externe                        |
| **Volume croissant, budget maîtrisé** | hybrid                   | Local pour tâches légères, API pour les pics |

## **Point de vigilance sur Groq**

Fin décembre 2025, Nvidia a licencié la technologie LPU de Groq et embauché son CEO et président fondateurs dans une transaction reportée à environ 20 milliards de dollars. Groq a déclaré que GroqCloud continuerait d'opérer sans interruption, mais la transaction a réduit substantiellement l'équipe technique de Groq, et le sentiment de la communauté parmi les utilisateurs API existants a évolué négativement.

La recommandation concrète : ne jamais architecturer une dépendance exclusive à Groq. Le gateway LiteLLM avec Together AI ou Fireworks AI en fallback est non négociable dès la première version de production.

# **Couche 3  Mémoire des Agents**

## **Pourquoi la mémoire est un enjeu à part entière**

Les LLMs sont sans état à leur cœur  le modèle lui-même ne retient aucune information entre les appels API. Des produits comme ChatGPT et Claude ajoutent des systèmes de mémoire par-dessus, c'est pourquoi ils se souviennent du nom et des préférences de l'utilisateur. Quand on construit ses propres agents, on doit implémenter cette couche mémoire soi-même.

Dans notre système marketing, les conséquences sont concrètes. Sans mémoire bien architecturée, l'Agent Content regénère des articles sur des thèmes déjà traités, l'Agent Email envoie des séquences déjà envoyées, l'Orchestrateur repart de zéro à chaque cycle hebdomadaire au lieu de capitaliser sur ce qu'il a appris, et un crash de serveur fait perdre l'état d'une campagne qui tournait depuis trois jours.

La mémoire n'est pas une chose unique. Les agents en production ont besoin de trois types de mémoire qui fonctionnent différemment, se dégradent différemment, et nécessitent des infrastructures différentes.

## **Les trois types de mémoire et leurs rôles**

| **Type**                          | **Analogie**                  | **Ce qu'il stocke**                                             | **Durée de vie**                         |
| --------------------------------- | ----------------------------- | --------------------------------------------------------------- | ---------------------------------------- |
| **Mémoire court terme**           | RAM d'un ordinateur           | État courant de la session, contexte immédiat                   | Durée de la session ou du thread         |
| **Mémoire long terme structurée** | Disque dur relationnel        | Historique campagnes, préférences, décisions, performances      | Permanente                               |
| **Mémoire sémantique**            | Bibliothèque indexée par sens | Contenus produits, connaissances métier, documents de référence | Permanente, interrogeable par similarité |

## **Mémoire court terme  Redis**

Redis est la technologie retenue pour la mémoire court terme. C'est un store in-memory open source qui donne aux agents une mémoire de travail ultrarapide.

### **Ce que Redis stocke dans notre système**

| **Donnée**                           | **Description**                                                      |
| ------------------------------------ | -------------------------------------------------------------------- |
| **État courant du thread LangGraph** | Le checkpoint actif de chaque agent en cours d'exécution             |
| **Contexte de session**              | Les échanges récents entre l'orchestrateur et les agents spécialisés |
| **File de tâches Celery**            | Les tâches asynchrones en attente ou en cours                        |
| **Cache de routage LiteLLM**         | Les décisions de routage LLM récentes pour éviter de recalculer      |
| **Résultats intermédiaires**         | Les outputs partiels d'un fanout parallèle avant consolidation       |

### **Pourquoi Redis**

La vitesse d'accès in-memory est le seul moyen de ne pas ajouter de latence perceptible entre les étapes des agents. À titre d'exemple, Relevance AI a réduit la latence de recherche vectorielle de 2 secondes à 10 millisecondes après avoir migré leur recherche vectorielle et leur caching vers Redis  une amélioration de 99,5 %.

Les agents en production ont typiquement besoin d'au moins deux couches : un cache in-memory (Redis) pour l'état de session rapide et les buffers de conversation, et une base de données vectorielle pour la récupération sémantique sur des historiques plus longs.

Redis a également évolué pour le cas d'usage agent en 2026. Redis a dévoilé le Context Engine, une couche mémoire dédiée aux agents IA d'entreprise composée de Redis Context Retriever, Redis Agent Memory, et Redis Data Integration. Le composant Agent Memory fournit un historique d'interactions court terme plus un cache mémoire de plus longue durée.

## **Mémoire long terme structurée  PostgreSQL**

PostgreSQL stocke tout ce qui doit persister de manière structurée et relationnelle sur le long terme.

### **Ce que PostgreSQL stocke dans notre système**

| **Table**                   | **Contenu**                                                                | **Utilisé par**          |
| --------------------------- | -------------------------------------------------------------------------- | ------------------------ |
| **Campagnes**               | Historique complet de toutes les campagnes  objectifs, budgets, résultats | Orchestrateur, Analytics |
| **Performances**            | KPIs par canal, par semaine, par campagne                                  | Analytics, Reporting     |
| **Ligne éditoriale**        | Ton, vocabulaire, charte, sujets à éviter                                  | Agent Content            |
| **Audiences**               | Segments, comportements, historique des séquences reçues                   | Agent Email              |
| **Mots-clés**               | Positions SEO historiques, opportunités identifiées                        | Agent SEO                |
| **Checkpoints LangGraph**   | États sauvegardés de tous les threads agents (PostgresSaver)               | LangGraph                |
| **Décisions orchestrateur** | Toutes les décisions d'allocation budgétaire et leurs résultats            | Orchestrateur            |

Dans l'écosystème LangGraph, des équipes remplacent les checkpointers Redis par des graphes d'état adossés à Postgres pour obtenir une mémoire d'agent durable et interrogeable sans introduire un second store de données. L'historique de conversation, les logs d'appels d'outils, et l'état structuré se retrouvent tous dans PostgreSQL.

La règle pratique qui émerge des retours de production : utiliser Postgres pour l'historique de conversation chronologique et l'état structuré (IDs utilisateurs, préférences, flags), et la mémoire vectorielle pour les faits sémantiques (compétences, instructions, entités nommées, documents). Cela maintient les données relationnelles rapides et explicables, tandis que la recherche vectorielle donne une récupération flexible basée sur le sens.

### **PostgreSQL comme backend des checkpoints LangGraph**

C'est un point technique critique. LangGraph utilise PostgresSaver en production pour persister l'état de chaque nœud après chaque exécution. Cela signifie que PostgreSQL est à la fois la base de données métier du système ET le backend de persistence des agents. Un seul composant, deux rôles, une seule infrastructure à maintenir.

## **Mémoire sémantique  Qdrant**

Qdrant est la base de données vectorielle retenue pour la mémoire sémantique. C'est là que le système stocke les représentations numériques (embeddings) de tout ce qu'il produit et connaît, pour pouvoir retrouver des informations par similarité de sens plutôt que par correspondance exacte.

### **Pourquoi la recherche sémantique est indispensable**

Un store clé-valeur ou documentaire échoue pour la mémoire des agents parce qu'il nécessite des correspondances exactes et perd la nuance sémantique. Si l'Agent Content veut savoir si un article similaire a déjà été produit, il ne peut pas chercher par mots-clés exacts  il doit chercher par sens. Une recherche de "erreurs similaires passées" doit correspondre à "limite de taux dépassée", "quota atteint" et "throttling actif"  un contexte qui nécessiterait autrement de bourrer des milliers de tokens dans chaque requête.

### **Ce que Qdrant stocke dans notre système**

| **Collection**             | **Contenu**                                                  | **Utilisé par**                        |
| -------------------------- | ------------------------------------------------------------ | -------------------------------------- |
| **Contenus produits**      | Embeddings de tous les articles, posts, emails générés       | Agent Content (éviter les doublons)    |
| **Connaissances marque**   | Embeddings de la ligne éditoriale, des produits, des valeurs | Tous les agents de contenu             |
| **Campagnes passées**      | Embeddings des campagnes et leurs résultats                  | Orchestrateur (apprendre des patterns) |
| **Mots-clés SEO**          | Embeddings des clusters thématiques                          | Agent SEO                              |
| **Comportements audience** | Embeddings des profils et patterns de conversion             | Agent Email                            |
| **Documents de référence** | Embeddings de tous les documents métier uploadés             | RAG cross-agents                       |

### **Pourquoi Qdrant et pas Pinecone ou Weaviate**

Qdrant est devenu le favori des développeurs pour construire des systèmes de mémoire d'agents. Écrit en Rust, il offre une latence négligeable avec une utilisation mémoire prévisible. Sa recherche filtrée rapide indexe les champs payload directement dans le graphe HNSW, empêchant l'effondrement du recall par sur-filtrage. La quantification binaire compresse les embeddings jusqu'à 32x, permettant une recherche vectorielle in-memory sur des millions de documents sur du matériel standard.

Qdrant est sous licence Apache 2.0, self-hostable, et c'est le vector store que l'écosystème n8n livre dans son starter kit officiel pour l'IA self-hosted, aux côtés d'Ollama et Postgres.

## **Comment les trois couches interagissent dans le système**

Voici un exemple concret pour illustrer le flux complet. L'Agent Content reçoit un brief de l'Agent SEO pour écrire un article sur "l'email marketing B2B en Afrique". Avant de générer quoi que ce soit, il interroge les trois couches mémoire dans l'ordre suivant :

**1\. Redis (court terme, < 1 ms) :** Y a-t-il un contexte de session en cours sur ce sujet ? Un autre agent a-t-il déjà travaillé dessus ce matin ?

**2\. Qdrant (sémantique, 10-50 ms) :** Des articles similaires ont-ils déjà été produits ? Recherche par similarité sémantique : trois articles proches sur "email marketing francophone" et "stratégie B2B Cameroun" sont récupérés pour éviter le doublonnage et assurer la complémentarité.

**3\. PostgreSQL (long terme, quelques ms) :** Quels sont les articles les plus performants historiquement sur ce type de thème ? Quelle est la longueur optimale ? Quel ton a généré le plus d'engagement ?

Avec ces trois contextes, l'Agent Content génère un article différent et complémentaire de l'existant, au bon format, dans le bon ton, avec les bonnes références internes.

## **Tableau de synthèse  Couche 3**

| **Composant**  | **Technologie**      | **Type mémoire**      | **Latence** | **Durée de vie** | **Rôle principal**                      |
| -------------- | -------------------- | --------------------- | ----------- | ---------------- | --------------------------------------- |
| **Redis**      | Redis 7+ open source | Court terme           | < 1 ms      | Session/thread   | État agents, cache, queues Celery       |
| **PostgreSQL** | PostgreSQL 16        | Long terme structurée | < 10 ms     | Permanente       | Historique, KPIs, checkpoints LangGraph |
| **Qdrant**     | Qdrant Apache 2.0    | Sémantique            | 10-50 ms    | Permanente       | Similarité contenu, RAG, mémoire marque |

## **Ce que cette architecture évite**

| **Problème sans mémoire**                                    | **Solution apportée**                                                    |
| ------------------------------------------------------------ | ------------------------------------------------------------------------ |
| **L'agent regénère des contenus déjà produits**              | Qdrant détecte la similarité avant génération                            |
| **Un crash fait perdre une campagne en cours**               | PostgresSaver + PostgreSQL récupèrent l'état exact                       |
| **L'orchestrateur repart de zéro chaque semaine**            | PostgreSQL conserve l'historique des performances et décisions           |
| **Les agents ignorent la ligne éditoriale**                  | Qdrant stocke les embeddings de la charte, récupérés à chaque génération |
| **L'Agent Email envoie des séquences déjà reçues**           | PostgreSQL trace toutes les séquences envoyées par contact               |
| **La mémoire de session est perdue si le serveur redémarre** | Redis persiste sur disque (AOF/RDB) en configuration production          |

# **Agent Créatif  Analyse approfondie**

## **Ce qu'on ajoute au système**

Il ne s'agit pas simplement d'ajouter une fonctionnalité à un agent existant. On ajoute un huitième agent à part entière : l'Agent Créatif. Il est sollicité par l'Agent Content pour toute production visuelle, et il reçoit ses instructions de l'Orchestrateur comme tous les autres agents.

Son rôle : produire des visuels marketing finaux, prêts à l'emploi pour les clients et les autres agents (Social, Email, SEA), en s'appuyant sur deux types d'inputs uploadés par le client.

## **Les deux sources d'alimentation**

### **Source 1  Templates structurels (Figma / Canva)**

Ce sont les gabarits de mise en page. Ils définissent la structure : où se place le titre, où va le logo, où va l'image principale, quelles zones sont réservées au texte, quelles dimensions pour quel format (post Instagram carré, bannière LinkedIn, affiche A3, visuel email).

L'API REST de Figma permet d'accéder programmatiquement à tous les fichiers de design, d'extraire les composants, les styles, et d'exporter les frames comme images PNG, JPG, SVG ou PDF. Concrètement, l'agent peut lire un template Figma, extraire sa structure, y injecter du contenu (texte, couleurs, images), et exporter le résultat final en PNG livrable.

Pour Canva, l'approche est similaire via leur API Connect qui permet la manipulation programmatique de templates et l'export en formats finaux.

### **Source 2  Affiches de référence stylistique (PNG/JPEG)**

Ce sont les créations existantes qui définissent l'identité visuelle : des affiches bien faites, des visuels qui ont bien fonctionné, des exemples du style que l'on veut reproduire ou dont on veut s'inspirer. C'est la réponse directe au problème du "rendu trop IA".

Ces images sont stockées dans Qdrant (couche mémoire sémantique) sous forme d'embeddings visuels. Quand l'agent doit créer un nouveau visuel, il interroge Qdrant pour retrouver les références les plus proches du brief en cours, et il s'en sert comme guides stylistiques.

## **La stack technique de l'Agent Créatif**

### **FLUX.2  le modèle de génération d'images**

FLUX.2, sorti en novembre 2025 par Black Forest Labs, marque un saut majeur de la génération d'images expérimentale vers une création visuelle véritablement adaptée à la production. C'est le modèle leader en qualité parmi les modèles open source en 2026.

Une fonctionnalité notable de FLUX.2 est sa capacité à combiner plusieurs images de référence dans un seul processus de génération. On peut fournir différents inputs  un design de personnage, un style artistique, et une image de produit  et le modèle les mélange sans nécessiter d'entraînement supplémentaire.

_Point de vigilance sur la licence : FLUX.2 dev nécessite une licence commerciale séparée via Black Forest Labs. Pour une utilisation commerciale sans restriction, FLUX.2 Schnell (version rapide, Apache 2.0) ou Qwen-Image (Apache 2.0, fort sur le rendu typographique) sont les alternatives à privilégier._

Pour le rendu de texte dans les images  titres sur les affiches, slogans, prix promotionnels  si la précision du texte dans les outputs générés est l'exigence principale, GLM-Image est l'option open source la plus capable disponible en 2026. Qwen-Image est le modèle à utiliser quand les images doivent contenir des mots lisibles. Alibaba a intégré le raisonnement linguistique et de mise en page dans l'architecture, ce qui permet de placer du texte propre à l'intérieur des affiches, étiquettes et signages.

### **ComfyUI  le moteur de workflow de génération**

ComfyUI est l'orchestrateur de la génération d'images. Il permet de construire des pipelines de génération en graphe de nœuds, exactement comme LangGraph orchestre les agents LLM. Dans notre cas, ComfyUI orchestre la chaîne : template + références stylistiques + prompt → image finale.

ComfyUI permet l'exécution de workflows de génération d'images complexes avec des modèles custom, des LoRAs, et des chaînes de traitement. Il supporte la création de contenu automatisée pour générer des visuels de produits, des contenus marketing ou des contenus réseaux sociaux à l'échelle, et l'intégration ControlNet pour des méthodes de conditioning avancées pour une génération d'images précise.

## **La réponse technique au problème du "rendu générique"**

Trois techniques combinées permettent d'éviter l'aspect générique.

### **IPAdapter  le transfert de style depuis les références**

IP-Adapter est utilisé pour transférer des styles artistiques depuis des images de référence vers de nouveaux sujets, maintenir la cohérence visuelle de marque à travers les assets marketing générés, guider l'ambiance et l'atmosphère à travers des références environnementales ou photographiques.

Concrètement : on uploade 5 à 10 affiches qui ont bien fonctionné. IPAdapter extrait leurs caractéristiques visuelles  palette de couleurs, style typographique, ambiance, composition  et injecte ces caractéristiques comme guide de génération. Le résultat ressemble aux créations existantes, pas à une image IA générique. Une consistance stable est atteinte avec 3 à 5 images de référence, sans coût d'entraînement.

### **ControlNet  le respect de la structure du template**

ControlNet permet de contraindre la génération à respecter la structure du template de mise en page. Si le template Figma définit qu'une zone en haut à gauche est réservée au titre et qu'une zone centrale accueille l'image principale, ControlNet s'assure que la génération respecte cette structure. Pour du travail produit qui nécessite la même mise en page à chaque fois, ce contrôle vaut plus qu'un léger avantage de qualité.

### **LoRA  l'identité visuelle d'une marque spécifique**

Pour les clients récurrents qui veulent une cohérence visuelle forte sur le long terme, on peut entraîner un LoRA sur leurs créations existantes. Sans un LoRA, on s'appuie sur des styles que le modèle de base connaît déjà de ses données d'entraînement. Les esthétiques génériques comme l'aquarelle, le cel shading, ou le film noir existeront typiquement dans les modèles de base, mais les styles propriétaires n'y seront pas. Avec un LoRA entraîné sur un style spécifique, on peut l'activer avec un mot déclencheur dans le prompt et le modèle génère nativement dans ce style.

## **Le tableau des modèles d'images retenus**

| **Modèle**              | **Licence** | **Force principale**              | **Usage dans le système**          |
| ----------------------- | ----------- | --------------------------------- | ---------------------------------- |
| **FLUX.2 Schnell**      | Apache 2.0  | Qualité générale, vitesse         | Génération principale d'affiches   |
| **Qwen-Image**          | Apache 2.0  | Texte lisible dans les images     | Visuels avec titres et slogans     |
| **GLM-Image**           | MIT         | Texte dense, typographie complexe | Affiches avec beaucoup de texte    |
| **Stable Diffusion XL** | OpenRAIL    | Écosystème LoRA le plus mature    | LoRA marque client, style transfer |

## **Le flux complet de l'Agent Créatif**

Le flux se déroule en cinq étapes enchaînées.

**Étape 1  Réception du brief :** l'Agent Content ou l'Orchestrateur envoie un brief : type de visuel (post Instagram, affiche événement, bannière email), objectif (promotion, notoriété, lancement produit), textes à intégrer (titre, slogan, CTA), format et dimensions.

**Étape 2  Sélection du template :** l'agent interroge la bibliothèque de templates Figma/Canva via API. Il sélectionne le template correspondant au format demandé et extrait sa structure  zones de texte, zones d'image, couleurs définies, typographie.

**Étape 3  Récupération des références stylistiques :** l'agent interroge Qdrant avec un embedding du brief. Il récupère les 3 à 5 affiches de référence les plus proches sémantiquement du brief en cours. Ces affiches alimentent IPAdapter pour le guidage stylistique.

**Étape 4  Génération ComfyUI :** le pipeline ComfyUI s'exécute : ControlNet reçoit la structure du template, IPAdapter reçoit les affiches de référence, le modèle FLUX.2/Qwen-Image reçoit le prompt textuel décrivant le visuel. La génération produit une image qui respecte la structure, s'inspire du style de référence, et intègre les textes demandés.

**Étape 5  Post-traitement et livraison :** l'image est upscalée si nécessaire (Real-ESRGAN open source), les textes sont validés lisibles, le fichier PNG final est stocké dans Qdrant (pour devenir lui-même une référence future) et livré aux agents qui en ont besoin (Social, Email, SEA).

## **Ce que le client uploade et comment ça s'organise**

| **Ce que le client uploade**          | **Format**                     | **Stocké dans**                            | **Utilisé par**           |
| ------------------------------------- | ------------------------------ | ------------------------------------------ | ------------------------- |
| **Templates de mise en page**         | Fichiers Figma (.fig) ou Canva | Figma/Canva API + PostgreSQL (métadonnées) | Étape 2  structure       |
| **Affiches de référence stylistique** | PNG, JPEG                      | Qdrant (embeddings visuels)                | Étape 3  style guide     |
| **Logo et éléments de marque**        | SVG, PNG                       | PostgreSQL + Qdrant                        | Intégration systématique  |
| **Charte graphique**                  | PDF, document texte            | PostgreSQL + Qdrant                        | Contraintes de génération |

## **Intégration dans le stack existant**

| **Composant**              | **Ajout**                                               | **Justification**                         |
| -------------------------- | ------------------------------------------------------- | ----------------------------------------- |
| **FLUX.2 / Qwen-Image**    | Nouveau modèle image (GPU partagé avec LLM si possible) | Génération visuelle                       |
| **ComfyUI**                | Nouveau service Docker                                  | Orchestration des pipelines de génération |
| **IPAdapter + ControlNet** | Extensions ComfyUI                                      | Style transfer + respect structure        |
| **Figma API / Canva API**  | Nouvelles intégrations dans n8n                         | Lecture templates, export PNG             |
| **Real-ESRGAN**            | Post-processing open source                             | Upscaling sans perte                      |
| **Qdrant**                 | Déjà présent  nouvelle collection visuelle             | Stockage embeddings images                |

## **Le stack image complet mis à jour dans la couche 2**

| **Type**            | **Modèle retenu**           | **Licence**     | **Usage**                    |
| ------------------- | --------------------------- | --------------- | ---------------------------- |
| **LLM complexe**    | Llama 3.3 70B               | Llama Community | Raisonnement, orchestration  |
| **LLM multilingue** | Qwen3.5 72B                 | Apache 2.0      | Contenu français             |
| **LLM léger**       | Mistral 7B                  | Apache 2.0      | Tâches simples               |
| **Image**           | FLUX.2 Schnell + Qwen-Image | Apache 2.0      | Génération visuels marketing |

# **Couche 4  Les outils marketing connectés**

## **Pourquoi cette couche est différente des autres**

Les couches 1, 2 et 3 constituent le cerveau et la mémoire du système. La couche 4 est ce qui connecte ce cerveau au monde réel. Sans elle, les agents raisonnent dans le vide. C'est ici que les agents agissent concrètement : publier un post, envoyer un email, récupérer des données SEO, lancer une campagne publicitaire.

Chaque outil de cette couche est une extension concrète d'un agent spécifique. n8n joue le rôle de passerelle universelle entre les agents et les plateformes externes.

## **L'architecture de la couche 4**

Tous les outils de cette couche sont accessibles depuis LangGraph via des appels d'outils (function calling). n8n sert de couche d'intégration centrale pour tout ce qui nécessite de la logique de workflow ou des connecteurs vers des plateformes tierces. Les APIs directes (Google Search Console, Google Ads, Meta) sont appelées directement depuis les agents sans passer par n8n quand la simplicité le permet.

```
LangGraph (Agents)
│
├── Appels directs APIs ──► Google Search Console
│                    ──► Google Ads API
│                    ──► Meta Marketing API
│
└── Via n8n ──────────────► Réseaux sociaux (LinkedIn, TikTok, Meta)
              ──────────────► Mautic (Email automation)
              ──────────────► Matomo (Analytics)
              ──────────────► SearXNG / Serper (Recherche web)
```

## **Outil 1  Matomo (Analytics)**

Matomo est depuis 2007 la plateforme d'analytics web open source la plus complète. Pour les organisations qui migrent depuis Google Analytics et souhaitent une expérience similaire sous leur propre contrôle, Matomo est la correspondance la plus proche.

L'Agent Analytics interroge Matomo via son API REST pour récupérer : le trafic par source, les conversions par canal, les comportements des visiteurs, les performances des pages, et les données d'attribution multi-touch. Toutes ces données alimentent les décisions de l'Orchestrateur et les rapports produits par l'Agent Reporting.

Les marketeurs accèdent à une segmentation de contenu exploitable, un suivi des performances de campagnes multi-canaux, et une analyse du ROI. Les développeurs obtiennent une collecte de données personnalisable, des APIs de reporting avancées, et la liberté de self-host et modifier l'ensemble du codebase.

_Point de vigilance sur la licence : le core de Matomo est GPLv3, sûr et protégé par copyleft. Les fonctionnalités enterprise incluant les Heatmaps, A/B Testing, l'intégration SAML/LDAP, et les connecteurs Data Warehouse sont vendus comme Plugins Premium propriétaires. Les fonctionnalités core suffisent largement pour notre système  pas besoin des plugins payants en première version._

## **Outil 2  Mautic (Email automation)**

Mautic est le projet d'automatisation marketing open source le plus large au monde. C'est une alternative self-hosted à HubSpot ou Marketo qui donne un contrôle total sur les données et les workflows de campagne.

Mautic gère la segmentation de contacts, les séquences d'emails automatisées déclenchées par comportements, le scoring de leads, le tracking des interactions sur le site, et les landing pages. L'Agent Email interagit avec Mautic via son API pour créer des segments, déclencher des campagnes, récupérer les statistiques d'ouverture et de clic, et gérer les désabonnements.

La version 7.1.2 (disponible en 2026) supporte une architecture dédiée avec des workers séparés pour le web, les tâches cron, et les queues, ce qui la rend adaptée à un déploiement Docker Compose de production.

Ce que Mautic remplace sans coût : Mailchimp (à partir de 300 \$/mois à volume), HubSpot Email (à partir de 800 \$/mois), ActiveCampaign. Pour des bases de contacts importantes, l'économie est substantielle sur le long terme.

## **Outil 3  n8n (Automatisation et intégrations)**

n8n est la pièce d'intégration centrale de toute la couche 4. C'est une plateforme d'automatisation de workflows open source, self-hostable, qui connecte des centaines d'applications et d'APIs via une interface visuelle en nœuds.

Ce qui distingue n8n de beaucoup d'autres solutions d'automatisation est le haut degré de contrôle et de flexibilité. La plateforme est self-hostable, évite le vendor lock-in, et peut être profondément personnalisée selon les besoins individuels. Particulièrement pour les organisations avec des exigences élevées en matière de protection des données, de liberté d'intégration, et de scalabilité à long terme, c'est un avantage décisif.

### **Ce que n8n orchestre dans notre système**

Pour le Social Media, n8n connecte les APIs de LinkedIn, Meta, TikTok, et Twitter/X pour la publication programmée, la récupération des métriques d'engagement, et l'écoute des mentions. Un workflow n8n de social media automation de production est un pipeline de contenu agentique complet qui génère, valide, route pour approbation, publie sur les plateformes, gère les échecs, et enregistre les résultats entièrement sans intervention manuelle.

Pour le SEO, n8n connecte Google Search Console, Ahrefs ou SEMrush (selon le budget client), et Matomo dans des pipelines planifiés qui suivent les classements, font des audits de site, et livrent des rapports hebdomadaires sans effort manuel. Les équipes SEO passent 40 % de leur temps sur des tâches que n8n automatise en quelques minutes.

Pour la veille concurrentielle, n8n scrape les SERPs via SearXNG ou Serper, surveille les publicités actives des concurrents, et alimente l'Agent SEO et l'Agent SEA avec des données fraîches.

n8n expose 2000+ templates de workflows prébuilt dans sa bibliothèque communautaire, dont plus de 580 dédiés aux réseaux sociaux seuls. Ce capital de templates accélère considérablement l'implémentation.

## **Outil 4  SearXNG (Recherche web self-hosted)**

SearXNG est un métamoteur de recherche open source qui agrège les résultats de Google, DuckDuckGo, Bing et d'autres sources. Les utilisateurs ne sont ni tracés ni profilés. Il s'utilise via une simple requête HTTP, sans clé API requise, et se déploie en Docker en quelques minutes.

Dans notre système, SearXNG alimente l'Agent SEO pour la veille des SERPs, l'Agent Social pour la détection des tendances, et l'Orchestrateur pour la veille concurrentielle générale. C'est l'option gratuite et totalement souveraine.

Pour les cas où la qualité et la fraîcheur des données SERP sont critiques (audit SEO approfondi, suivi de positions), Serper API complète SearXNG : tier gratuit à 2 500 recherches, payant à partir de 50 \$/mois pour 50 000 recherches, avec une réponse moyenne de moins de 3 secondes et un output JSON propre.

## **Outil 5  Google Search Console API (SEO)**

L'API Google Search Console est gratuite à utiliser et donne accès aux données officielles de Google : impressions, clics, positions moyennes, pages indexées, erreurs d'exploration. C'est la source la plus fiable pour le suivi des performances SEO.

L'Agent SEO l'interroge régulièrement pour alimenter l'Agent Analytics, détecter les chutes de positions, identifier les pages sous-performantes et les opportunités de mots-clés avec un fort potentiel de progression.

_Point technique : Google a supprimé le paramètre num=100 le 11 septembre 2025, forçant chaque API SERP à paginer 10 résultats à la fois au lieu de 100. Les coûts d'infrastructure ont augmenté d'environ 10 fois du jour au lendemain pour les outils de suivi de classement. À intégrer dans la conception des workflows de suivi._

## **Outil 6  Google Ads API et Meta Marketing API (SEA)**

Ces deux APIs sont imposées par les plateformes. Il n'existe pas d'alternative open source crédible pour gérer des campagnes publicitaires sur Google et Meta. Les APIs sont gratuites à utiliser, le coût est celui des clics.

L'Agent SEA les utilise pour créer et modifier les campagnes, ajuster les enchères, générer et tester des variantes d'annonces, et récupérer les métriques de performance (CPA, ROAS, CTR) pour les transmettre à l'Agent Analytics.

## **Tableau de synthèse  Couche 4**

| **Outil**                     | **Type**                 | **Licence**                         | **Rôle**                                   | **Agent concerné** |
| ----------------------------- | ------------------------ | ----------------------------------- | ------------------------------------------ | ------------------ |
| **Matomo**                    | Analytics web            | GPLv3                               | Tracking trafic, conversions, attribution  | Agent Analytics    |
| **Mautic**                    | Email automation         | GPLv3                               | Segmentation, séquences, scoring leads     | Agent Email        |
| **n8n**                       | Automatisation workflows | Sustainable Use (self-host gratuit) | Intégrations sociales, SEO, veille         | Tous les agents    |
| **SearXNG**                   | Métamoteur recherche     | AGPLv3                              | Veille SERP, tendances, concurrence        | Agent SEO, Social  |
| **Serper API**                | API SERP                 | Commerciale (tier gratuit)          | Données SERP qualité production            | Agent SEO          |
| **Google Search Console API** | API officielle           | Gratuite                            | Positions, impressions, erreurs indexation | Agent SEO          |
| **Google Ads API**            | API officielle           | Gratuite (clics payants)            | Gestion campagnes search                   | Agent SEA          |
| **Meta Marketing API**        | API officielle           | Gratuite (clics payants)            | Gestion campagnes social                   | Agent SEA          |
| **Figma API / Canva API**     | API design               | Commerciale (tier gratuit)          | Templates visuels                          | Agent Créatif      |
| **ComfyUI**                   | Génération images        | GPLv3                               | Pipeline génération visuels                | Agent Créatif      |

## **Ce que n8n remplace concrètement**

| **Outil SaaS remplacé**        | **Coût mensuel typique**       | **Remplacé par**                         |
| ------------------------------ | ------------------------------ | ---------------------------------------- |
| **Zapier / Make**              | 50 à 600 \$/mois               | n8n self-hosted (gratuit)                |
| **Hootsuite / Buffer**         | 50 à 250 \$/mois               | n8n + APIs sociales directes             |
| **Mailchimp / ActiveCampaign** | 300 à 1 500 \$/mois            | Mautic self-hosted (gratuit)             |
| **Google Analytics 4**         | Gratuit mais données partagées | Matomo self-hosted (souveraineté totale) |

# **Couche 5  Infrastructure**

## **Vue d'ensemble de la couche**

La couche 5 est la couche qui maintient tout le reste en vie. Elle ne produit rien directement pour l'utilisateur final, mais sans elle, les campagnes échouent silencieusement, les agents se bloquent, les erreurs passent inaperçues et les crashes font perdre des heures de travail. Elle se décompose en trois blocs distincts mais complémentaires : les queues de tâches asynchrones, le monitoring LLM, et le monitoring infrastructure.

## **Bloc 1  Queues de tâches : Celery + Redis**

### **Pourquoi les queues sont indispensables dans notre système**

La génération d'un article de 2 000 mots par un LLM 70B prend entre 30 secondes et 3 minutes. L'envoi d'une séquence email à 10 000 contacts prend plusieurs minutes. La génération d'une affiche par l'Agent Créatif peut prendre 60 à 90 secondes. Ces tâches ne peuvent pas bloquer le thread principal de l'application. Sans queue asynchrone, un utilisateur qui déclenche une campagne attend plusieurs minutes devant un écran vide, et un crash à mi-chemin perd tout le travail.

Le cycle de traitement d'une requête HTTP dépasse rarement 30 secondes avant que les load balancers ne coupent la connexion. Les workloads LLM opèrent en secondes, pas en millisecondes. Celery et Redis résolvent ce problème fondamental.

### **Ce qu'est Celery**

Celery est la queue de tâches distribuée la plus largement utilisée pour Python, propulsant les jobs en arrière-plan chez Instagram, Mozilla et Robinhood. Avec plus de 25 800 étoiles GitHub et le support de Redis et RabbitMQ comme brokers de messages, Celery gère tout, de l'envoi d'emails au traitement de pipelines de machine learning.

La version stable actuelle est Celery 5.6.3 (sortie début 2026), qui supporte Python 3.9 à 3.13 et inclut le support des modèles Pydantic pour les arguments de tâches.

### **L'architecture Celery + Redis dans notre système**

L'architecture se décompose en quatre couches enchaînées. L'API FastAPI reçoit les requêtes et les envoie dans la queue Redis sans attendre le résultat. Redis stocke les tâches en mémoire et les distribue aux workers disponibles. Les workers Celery exécutent les tâches : appels LLM, génération d'images, envois email, publications sociales. PostgreSQL conserve les résultats persistants et l'historique des exécutions.

### **Les queues par type de tâche**

Dans notre système, toutes les tâches ne sont pas égales. Certaines sont critiques et urgentes, d'autres sont longues et tolèrent l'attente. Celery gère plusieurs queues indépendantes avec des workers dédiés selon la priorité.

| **Queue**            | **Tâches**                      | **Workers dédiés**   | **Priorité** |
| -------------------- | ------------------------------- | -------------------- | ------------ |
| **orchestration**    | Décisions de l'Orchestrateur    | 2-3 workers          | Haute        |
| **llm_inference**    | Appels LLM (génération contenu) | Selon GPU disponible | Haute        |
| **image_generation** | Agent Créatif (ComfyUI)         | 1-2 workers GPU      | Moyenne      |
| **email_dispatch**   | Envois Mautic                   | 2 workers            | Moyenne      |
| **social_publish**   | Publications n8n                | 2 workers            | Moyenne      |
| **analytics**        | Agrégation données, rapports    | 1 worker             | Basse        |
| **seo_tasks**        | Audits, recherche mots-clés     | 1 worker             | Basse        |

Cette séparation permet de scaler les workers critiques indépendamment sans affecter les tâches de fond. On peut lancer plusieurs containers de workers LLM sans toucher aux workers email.

### **Idempotence et retries**

Un principe fondamental dans notre système : chaque tâche doit être sûre à exécuter plusieurs fois. Pour les écritures en base de données, utiliser des opérations upsert plutôt que des insertions pures. Pour les appels à des APIs externes, vérifier l'état avant d'envoyer. Stocker une clé de déduplication sur chaque tâche et ignorer l'exécution si elle a déjà été traitée.

La configuration de retry avec backoff exponentiel évite de saturer les APIs externes lors d'une panne temporaire. Si Groq est temporairement indisponible, les tâches sont retentées après 1 minute, puis 5 minutes, puis 15 minutes, avant d'être marquées en échec et d'alerter l'Orchestrateur.

### **Flower  le dashboard de monitoring Celery**

Flower est l'interface web de monitoring de Celery, open source, qui s'intègre nativement. Il affiche les workers actifs, le débit des tâches, les taux de succès et d'échec, les tâches actives versus en queue, et permet de révoquer des tâches depuis l'interface. Flower se déploie comme un container Docker supplémentaire, accessible sur le port 5555, sans configuration supplémentaire.

## **Bloc 2  Monitoring LLM : LangFuse**

### **Ce qu'est LangFuse**

LangFuse est une plateforme d'ingénierie IA open source. Le tracing, la gestion des prompts, l'évaluation, et les expériences sont nativement intégrés, du prototype à la production. L'ensemble des fonctionnalités produit a été open-sourcé sous la licence MIT.

LangFuse traite plus de 90 milliards d'observations par mois et est utilisé par 21 des Fortune 50. Ses images Docker ont été téléchargées plus de 38 millions de fois.

### **Ce que LangFuse trace dans notre système**

LangFuse capture chaque appel LLM de chaque agent : le modèle utilisé, le prompt exact, la réponse, la latence, le nombre de tokens consommés, le coût estimé, et le résultat de l'évaluation de qualité. Pour un système multi-agents comme le nôtre, cette granularité est ce qui permet de déboguer en production sans avoir à reproduire les erreurs localement.

La vue graphe d'agent de LangFuse transforme une trace en image de ce que l'agent a fait : des nœuds pour les étapes, des arêtes pour la façon dont l'exécution s'est déplacée entre eux. LangFuse infère le graphe automatiquement à partir des timings et de l'imbrication des observations, et cela apparaît automatiquement pour l'intégration LangGraph.

### **Ce que LangFuse fournit concrètement dans notre contexte**

Pour chaque cycle de campagne, LangFuse permet de répondre aux questions suivantes : quel agent a consommé le plus de tokens cette semaine ? Quel prompt génère les contenus les mieux notés ? Quelle est la latence moyenne de l'Agent Content par rapport à l'Agent Analytics ? Quels appels LLM coûtent le plus cher et peuvent être routés vers un modèle plus léger ?

### **Alertes LangFuse**

Depuis juin 2026, LangFuse supporte des moniteurs à seuil sur les métriques de l'application LLM. Il est possible de détecter un pic de coût soudain quand le coût moyen par trace dépasse un seuil, une chute de qualité quand un score d'évaluation tombe en dessous de la cible, et une régression de latence quand la latence p95 pour un modèle dépasse le SLA défini. Les notifications arrivent via Slack, webhook, ou GitHub Actions.

### **Déploiement LangFuse**

Pour un déploiement local via Docker Compose, LangFuse tourne en 5 minutes. Pour la production via Kubernetes avec Helm, c'est le déploiement préféré. Dans notre Docker Compose, LangFuse s'ajoute comme deux containers : le serveur web et le worker d'ingestion asynchrone. Il utilise PostgreSQL (déjà présent dans notre stack) pour stocker les traces.

## **Bloc 3  Monitoring infrastructure : Prometheus + Grafana**

### **Le standard de l'industrie**

Prometheus et Grafana constituent le standard de monitoring infrastructure open source avec 75 % d'adoption sur Kubernetes. Prometheus collecte et stocke les métriques depuis l'infrastructure. Grafana transforme ces métriques en dashboards et alertes exploitables.

### **Ce que Prometheus scrape dans notre système**

| **Composant monitoré** | **Exporter**          | **Métriques clés**                             |
| ---------------------- | --------------------- | ---------------------------------------------- |
| **Serveur Linux**      | Node Exporter         | CPU, RAM, disque, réseau                       |
| **Containers Docker**  | cAdvisor              | CPU/RAM par container, restarts                |
| **Redis**              | Redis Exporter        | Mémoire utilisée, ops/sec, latence             |
| **PostgreSQL**         | Postgres Exporter     | Connexions actives, requêtes lentes, taille DB |
| **Celery workers**     | Flower Exporter       | Tâches en queue, workers actifs, taux d'échec  |
| **vLLM**               | vLLM metrics endpoint | Tokens/sec, temps d'inférence, VRAM utilisée   |
| **n8n**                | n8n metrics           | Workflows exécutés, erreurs                    |

### **Grafana  les dashboards**

Grafana se connecte à Prometheus comme datasource et affiche tous ces métriques dans des dashboards visuels. Il existe des milliers de dashboards préconstruits dans la bibliothèque communautaire Grafana pour chaque exporter listé ci-dessus. Dans notre cas, trois dashboards sont prioritaires : un dashboard opérationnel (état de santé de tous les containers), un dashboard LLM (tokens/sec, VRAM, latences d'inférence), et un dashboard business (campagnes en cours, tâches en queue, budget consommé).

### **Alertmanager  les notifications**

Alertmanager gère le routage des alertes quand les seuils sont dépassés. Il évite les duplications d'alertes, gère les silences planifiés (maintenance), et route les notifications vers les bons canaux : Slack pour les alertes techniques, email pour les alertes business critiques.

## **La structure Docker Compose complète**

Tout le système tourne dans Docker Compose. Chaque composant est un service distinct, isolé dans son container, communicant via un réseau bridge interne.

| **Service**              | **Image**          | **Rôle**                                 |
| ------------------------ | ------------------ | ---------------------------------------- |
| **langgraph_api**        | Custom Python      | API FastAPI + LangGraph                  |
| **celery_worker_llm**    | Custom Python      | Workers inférence LLM                    |
| **celery_worker_email**  | Custom Python      | Workers email Mautic                     |
| **celery_worker_social** | Custom Python      | Workers publications sociales            |
| **celery_worker_image**  | Custom Python      | Workers Agent Créatif                    |
| **celery_beat**          | Custom Python      | Scheduler tâches périodiques             |
| **flower**               | mher/flower        | Dashboard monitoring Celery              |
| **redis**                | redis:7-alpine     | Broker Celery + mémoire court terme      |
| **postgres**             | postgres:16        | BDD principale + checkpoints LangGraph   |
| **qdrant**               | qdrant/qdrant      | Mémoire sémantique                       |
| **vllm**                 | vllm/vllm-openai   | Inférence LLM locale (mode local/hybrid) |
| **comfyui**              | Custom             | Agent Créatif pipeline images            |
| **langfuse_web**         | langfuse/langfuse  | Interface + API LangFuse                 |
| **langfuse_worker**      | langfuse/langfuse  | Worker ingestion traces                  |
| **matomo**               | matomo:latest      | Analytics web                            |
| **mautic**               | mautic/mautic      | Email automation                         |
| **n8n**                  | n8nio/n8n          | Automatisation workflows                 |
| **prometheus**           | prom/prometheus    | Collecte métriques                       |
| **grafana**              | grafana/grafana    | Dashboards + alertes                     |
| **alertmanager**         | prom/alertmanager  | Routage notifications                    |
| **cadvisor**             | gcr.io/cadvisor    | Métriques containers                     |
| **node_exporter**        | prom/node-exporter | Métriques serveur                        |

## **Tableau de synthèse  Couche 5**

| **Composant**            | **Outil**               | **Licence** | **Rôle**                               |
| ------------------------ | ----------------------- | ----------- | -------------------------------------- |
| **Queue tâches**         | Celery 5.6              | BSD         | Distribution tâches asynchrones agents |
| **Broker**               | Redis 7                 | BSD-3       | Broker Celery + mémoire court terme    |
| **Scheduler**            | Celery Beat             | BSD         | Tâches périodiques (rapports, audits)  |
| **Dashboard Celery**     | Flower                  | BSD         | Monitoring workers et tâches           |
| **Monitoring LLM**       | LangFuse                | MIT         | Traces agents, coûts, qualité, prompts |
| **Monitoring infra**     | Prometheus              | Apache 2.0  | Collecte métriques tous composants     |
| **Dashboards**           | Grafana                 | AGPLv3      | Visualisation + alertes                |
| **Notifications**        | Alertmanager            | Apache 2.0  | Routage alertes Slack/email            |
| **Métriques containers** | cAdvisor                | Apache 2.0  | CPU/RAM par container Docker           |
| **Métriques serveur**    | Node Exporter           | Apache 2.0  | CPU/RAM/disque serveur hôte            |
| **Conteneurisation**     | Docker + Docker Compose | Apache 2.0  | Isolation et déploiement services      |

## **Ce que cette couche garantit concrètement**

| **Risque sans couche 5**               | **Mitigation apportée**                                      |
| -------------------------------------- | ------------------------------------------------------------ |
| **Agent bloqué sur une tâche longue**  | Celery isole chaque tâche dans un worker dédié               |
| **Crash perd une génération en cours** | Celery retry + Redis persistence récupèrent la tâche         |
| **Coût LLM explose sans le savoir**    | LangFuse alerte dès dépassement de seuil                     |
| **Prompt régressé en production**      | LangFuse compare qualité avant/après déploiement             |
| **Serveur sature à 3h du matin**       | Prometheus + Alertmanager envoient l'alerte Slack            |
| **Container redémarre en boucle**      | cAdvisor + Grafana détectent le pattern et alertent          |
| **Disque plein sur le serveur DB**     | Node Exporter + Alertmanager préviennent avant la saturation |
| **Workers Celery en starvation**       | Flower + Prometheus visualisent la queue en temps réel       |

# **Couche 6  Interface React**

## **Ce que l'interface doit accomplir**

La couche 6 n'est pas un simple dashboard d'affichage. C'est la surface de contrôle complète de la plateforme  l'endroit où l'humain fixe les objectifs, supervise les agents, valide les décisions sensibles, consulte les performances, et intervient si nécessaire. Elle doit être pensée pour trois profils d'utilisateurs distincts : le marketeur qui utilise la plateforme au quotidien sans expertise technique, le responsable qui veut des rapports et des KPIs, et l'administrateur qui configure les agents et gère les intégrations.

L'interface doit maîtriser cinq fonctions fondamentales spécifiques aux systèmes multi-agents : la visibilité de la planification (que font les agents en ce moment ?), la divulgation des actions d'outils (quels outils ont été appelés et avec quels résultats ?), la supervision de la mémoire (qu'est-ce que le système mémorise ?), le suivi des workflows multi-étapes (où en est la campagne ?), et le routage de récupération (que faire quand quelque chose échoue ?).

## **Stack technique retenu**

| **Composant**                | **Technologie**        | **Rôle**                            |
| ---------------------------- | ---------------------- | ----------------------------------- |
| **Framework**                | React 19 + TypeScript  | Fondation interface                 |
| **Styling**                  | Tailwind CSS v4        | Mise en forme rapide et cohérente   |
| **Composants UI**            | shadcn/ui              | Composants accessibles et thémables |
| **Graphiques**               | Recharts               | Visualisations KPIs, performances   |
| **Communication temps réel** | WebSocket + SSE        | Streaming agents, HITL, logs        |
| **API backend**              | FastAPI                | Endpoint REST + WebSocket server    |
| **State management**         | Zustand ou React Query | État global + cache données serveur |
| **Routing**                  | React Router v7        | Navigation entre sections           |

React reste le choix dominant pour les dashboards admin en 2026. Le modèle de composants s'applique naturellement aux interfaces de supervision, l'écosystème couvre chaque cas d'usage, et le pool de développeurs est le plus large de n'importe quel framework frontend.

Tailwind CSS v4 sortie en 2026 apporte de meilleures performances et un système de variables CSS natif. shadcn/ui est devenu le standard de facto pour les dashboards React modernes : composants accessibles, thémables, et entièrement contrôlables, construits avec Tailwind CSS.

Les WebSockets ont l'avantage sur HTTP pour les agents IA : les utilisateurs voient les tokens en temps réel au lieu de regarder un indicateur de chargement pendant 5 à 30 secondes. Les Server-Sent Events (SSE) sont une alternative légère pour les flux unidirectionnels.

## **L'architecture de l'interface  cinq sections**

### **Section 1  Tableau de bord principal**

C'est l'écran d'accueil de la plateforme. Il présente en un coup d'œil l'état global de la plateforme : objectifs de la semaine en cours et leur avancement, budget consommé versus budget alloué par canal, performances clés (trafic, leads, conversions) en données temps réel depuis Matomo, alertes actives remontées par l'Agent Analytics, et état de santé des agents (actifs, en attente, en erreur).

Les KPIs clés s'affichent sous forme de cartes compactes en haut de l'écran : trafic organique de la semaine, leads générés, taux de conversion, coût par acquisition, et ROAS des campagnes payantes. Chaque carte est cliquable et ouvre un détail analytique.

### **Section 2  Centre de contrôle des agents**

C'est le cœur de la supervision. Cette section affiche en temps réel ce que chaque agent fait, a fait, et va faire.

Pour chaque agent (Orchestrateur, SEO, SEA, Content, Social, Email, Analytics, Créatif), une carte dédiée affiche son statut courant (actif, en attente, en pause, en erreur), la tâche en cours avec sa progression, les dernières actions exécutées, et les prochaines tâches planifiées. Un fil d'activité en temps réel via WebSocket montre le flux des événements au fur et à mesure qu'ils se produisent : l'Agent Content vient de générer un article, l'Agent SEO a détecté une opportunité de mot-clé, l'Orchestrateur a réalloué 200 € du SEA vers le Content.

La visualisation du graphe LangGraph apparaît ici : les nœuds actifs en vert, ceux en attente en orange, ceux en erreur en rouge. L'utilisateur peut voir l'état du graphe en direct.

### **Section 3  Validation humaine (HITL)**

C'est la section la plus critique pour la confiance dans le système. Chaque fois qu'un agent déclenche un checkpoint interrupt() dans LangGraph, une notification apparaît ici avec tous les éléments nécessaires pour prendre une décision.

Les types de validations qui remontent dans cette section : campagne publicitaire avec un budget supérieur au seuil défini, contenu généré avant publication (si l'option est activée), réponse à une crise de réputation détectée sur les réseaux sociaux, réallocation budgétaire majeure proposée par l'Orchestrateur, et rapport hebdomadaire avant envoi au client.

Chaque validation présente le contexte complet : pourquoi l'agent a pausé, ce qu'il propose, les alternatives possibles, et l'impact estimé de chaque décision. L'utilisateur valide, modifie, ou rejette avec un commentaire. Sa décision reprend le fil d'exécution du graphe LangGraph.

Ce mécanisme reflète le principe de délégation progressive : le système gagne la permission à travers la fiabilité démontrée plutôt qu'en la demandant au lancement. Au fil du temps et des validations, l'utilisateur peut élever le seuil d'autonomie de chaque agent.

### **Section 4  Gestion des campagnes et contenus**

Cette section donne accès à tout ce que les agents ont produit et planifié. La vue calendrier éditorial affiche les publications programmées sur tous les canaux dans une vue mensuelle et hebdomadaire. L'utilisateur peut voir d'un coup d'œil la densité de contenu par canal, identifier les trous, et reprogrammer manuellement des éléments si nécessaire.

La bibliothèque de contenus liste tous les articles, posts, emails, et visuels produits avec leur statut (brouillon, en validation, publié, archivé), leurs performances (vues, clics, conversions), et un accès direct à chaque item pour modification manuelle si nécessaire.

La section campagnes SEA présente les campagnes actives sur Google et Meta avec leurs métriques en temps réel : dépense quotidienne, CPA, ROAS, et la courbe d'évolution sur les 30 derniers jours.

### **Section 5  Configuration et paramètres**

Cette section est réservée à l'administrateur. Elle permet de configurer le mode LLM (local, api, hybrid), les seuils de déclenchement des validations humaines, les clés API des fournisseurs, les templates de la ligne éditoriale, l'upload des affiches de référence et des templates Figma pour l'Agent Créatif, les budgets par canal et les alertes associées, et la gestion des accès multi-utilisateurs.

## **La communication temps réel**

Le streaming temps réel est désormais une attente standard. Les utilisateurs veulent voir l'agent travailler au fur et à mesure que les tokens s'écoulent, pas attendre des réponses complètes.

L'interface utilise deux mécanismes selon le cas d'usage. Les WebSockets pour la communication bidirectionnelle : suivi de l'état des agents, logs d'activité en direct, progression des tâches Celery, et les interactions HITL où l'utilisateur envoie une décision et reçoit immédiatement la reprise du workflow. Les Server-Sent Events (SSE) pour les flux unidirectionnels : streaming des tokens LLM lors de la génération de contenu visible dans l'interface, progression d'une génération d'image ComfyUI, et mises à jour de statut des publications sociales.

La connexion WebSocket utilise des types d'événements structurés : agent_status pour les changements d'état des agents, task_progress pour la progression des tâches Celery, hitl_interrupt pour les demandes de validation humaine, content_stream pour le streaming des tokens LLM, et alert pour les notifications critiques.

## **Les cinq fonctions UX spécifiques aux agents IA**

**La visibilité de la planification :** l'interface montre toujours le plan de l'Orchestrateur pour la semaine, les tâches assignées à chaque agent, et l'avancement. L'utilisateur ne découvre pas ce que le système a fait après coup  il le voit pendant.

**La divulgation des actions d'outils :** quand l'Agent SEO appelle l'API Google Search Console ou quand l'Agent SEA modifie une enchère, l'interface affiche l'action, ses paramètres, et son résultat. Aucune boîte noire.

**Le surfaçage de la mémoire :** une section dédiée permet de consulter ce que le système sait sur la marque du client, les campagnes passées, et les apprentissages accumulés. L'utilisateur peut corriger une information erronée ou supprimer un apprentissage obsolète.

**Le suivi des workflows multi-étapes :** pour chaque campagne en cours, une timeline visuelle montre les étapes accomplies, l'étape en cours, et les étapes à venir. Si une étape a échoué, la timeline indique pourquoi et ce que le système a fait pour récupérer.

**Le routage de récupération :** quand quelque chose échoue, l'interface présente clairement l'erreur, ce que le système a tenté comme récupération automatique, et si une intervention humaine est nécessaire.

## **Tableau de synthèse  Couche 6**

| **Composant**                | **Technologie**        | **Rôle**                            |
| ---------------------------- | ---------------------- | ----------------------------------- |
| **Framework**                | React 19 + TypeScript  | Fondation interface                 |
| **Styling**                  | Tailwind CSS v4        | Mise en forme rapide et cohérente   |
| **Composants UI**            | shadcn/ui              | Composants accessibles et thémables |
| **Graphiques**               | Recharts               | Visualisations KPIs, performances   |
| **Communication temps réel** | WebSocket + SSE        | Streaming agents, HITL, logs        |
| **API backend**              | FastAPI                | Endpoint REST + WebSocket server    |
| **State management**         | Zustand ou React Query | État global + cache données serveur |
| **Routing**                  | React Router v7        | Navigation entre sections           |

## **Ce que l'utilisateur ne voit pas mais qui est là**

Toute la complexité technique  LangGraph, Celery, Redis, PostgreSQL, Qdrant, vLLM, ComfyUI  est invisible depuis l'interface. L'utilisateur voit des agents qui travaillent, des contenus qui se créent, des campagnes qui s'optimisent, et des résultats qui s'améliorent. Il interagit avec des objectifs, des validations, et des rapports  pas avec des queues de tâches ou des vecteurs d'embedding.

C'est le contrat fondamental de la plateforme : toute la complexité du stack en arrière-plan, toute la simplicité dans ce que l'humain touche.

_Nexus · Architecture Technique v1.0 · 2026 · Document confidentiel_