"""Prompts de l'Orchestrateur, versionnés via LangFuse Prompt Management.

Chaque prompt est géré côté LangFuse (nom = la clé de `_FALLBACKS`, ex.
"parse-objective") pour permettre l'itération sans redéploiement du code. La
constante Python ci-dessous n'est qu'un FALLBACK, utilisé automatiquement si
LangFuse est injoignable ou si le prompt n'y existe pas encore
(`Langfuse.get_prompt(..., fallback=...)` gère cette bascule nativement).

Syntaxe des variables : `{{variable}}` (double accolade), volontairement
identique à la syntaxe native de LangFuse Prompt Management (vérifié dans le
SDK : `langfuse.model.TemplateParser`)  un fallback ci-dessous est donc
copiable tel quel dans l'UI LangFuse sans réécriture.
"""

from backend.llm.gateway.prompt_loader import get_prompt

PARSE_OBJECTIVE_PROMPT = """Tu es l'Orchestrateur de la plateforme NEXUS AI, une plateforme d'agents IA pour le marketing digital.

Un objectif business en langage naturel t'est fourni par le client. Ton rôle est de le décomposer en un plan structuré exploitable par les agents spécialisés (SEO, SEA, Content, Social, Email, Analytics, Reporting, Créatif).

OBJECTIF FOURNI : {{objective}}
BUDGET DISPONIBLE (si mentionné) : {{budget}}
PÉRIODE (si mentionnée) : {{period}}

Extrait et retourne un objet JSON strict avec les clés suivantes :
- "budget" : montant total en euros (nombre), déduit de l'objectif si non fourni explicitement, sinon celui fourni
- "period_start" et "period_end" : dates ISO 8601, déduites du contexte (ex. "ce mois-ci", "le trimestre prochain") si non fournies explicitement
- "priority_channels" : liste des canaux marketing prioritaires pour cet objectif, parmi ["seo", "sea", "content", "social", "email"]
- "target_kpis" : dict des KPIs cibles et leur valeur numérique visée (ex. {"organic_traffic_growth": 20} pour "+20% de trafic organique")

Ne retourne QUE le JSON, sans texte avant ou après."""


PLAN_WEEK_PROMPT = """Tu es l'Orchestrateur de la plateforme NEXUS AI. Tu dois produire le plan hebdomadaire d'une campagne, en tenant compte de l'historique des campagnes similaires.

OBJECTIF : {{objective}}
BUDGET : {{budget}}
CANAUX PRIORITAIRES : {{channels}}
HISTORIQUE DE CAMPAGNES SIMILAIRES (PostgreSQL) : {{historical_campaigns}}

Pour chaque canal prioritaire, produis une entrée de plan avec :
- "agent" : le nom de l'agent responsable (seo, sea, content, social, email, analytics, reporting, creative)
- "task_type" : le type de tâche à accomplir
- "priority" : 1 (le plus prioritaire) à 5 (le moins prioritaire)
- "deadline" : date ISO 8601 limite pour cette tâche dans la semaine
- "dependencies" : liste des task_type devant être complétés avant celui-ci (ex. les briefs de contenu dépendent des mots-clés SEO)

Appuie-toi sur l'historique de campagnes similaires pour calibrer les priorités et les délais si des patterns pertinents en ressortent.

Retourne un JSON strict : {"plan": [...]} où chaque élément suit le format ci-dessus. Ne retourne QUE le JSON."""


CHECK_PERFORMANCE_PROMPT = """Tu es l'Orchestrateur de la plateforme NEXUS AI. Tu dois évaluer si les performances actuelles d'une campagne justifient un ajustement.

KPIs CIBLES : {{target_kpis}}
KPIs ACTUELS : {{current_kpis}}
PÉRIODE ÉCOULÉE : {{period}}

Pour chaque KPI, calcule l'écart relatif entre la valeur actuelle et la cible. Un écart de plus de 20% (dans le sens défavorable) justifie une réallocation budgétaire vers les canaux sous-performants ou un renforcement des canaux performants.

Retourne un JSON strict avec :
- "requires_reallocation" : booléen, true si au moins un KPI présente un écart > 20%
- "underperforming_channels" : liste des canaux en écart défavorable > 20%
- "overperforming_channels" : liste des canaux en écart favorable > 20%
- "reasoning" : explication concise (2-3 phrases) de ton analyse

Ne retourne QUE le JSON."""


CRISIS_RESPONSE_PROMPT = """Tu es l'Orchestrateur de la plateforme NEXUS AI. Une situation de crise a été détectée (anomalie sévère, alerte critique, ou signal de réputation négatif) et nécessite une réponse immédiate.

CONTEXTE DE LA CRISE : {{crisis_context}}
CLIENT : {{client_name}}

Ton rôle : produire un plan de réponse de crise structuré, pas le contenu final publié (celui-ci reste soumis à validation humaine).

Retourne un JSON strict avec :
- "severity" : "low" | "medium" | "high" | "critical"
- "suspend_publications" : booléen, true si toutes les publications programmées doivent être suspendues immédiatement
- "response_summary" : résumé de la réponse recommandée (3-5 phrases), à valider par un humain avant toute publication
- "notify_team" : booléen, true si l'équipe humaine doit être notifiée immédiatement (quasi toujours true en pratique)

Ne retourne QUE le JSON."""


_FALLBACKS: dict[str, str] = {
    "parse-objective": PARSE_OBJECTIVE_PROMPT,
    "plan-week": PLAN_WEEK_PROMPT,
    "check-performance": CHECK_PERFORMANCE_PROMPT,
    "crisis-response": CRISIS_RESPONSE_PROMPT,
}


def get_orchestrator_prompt(name: str, **variables: object) -> str:
    """Récupère un prompt versionné depuis LangFuse (nom parmi `_FALLBACKS`),
    avec repli automatique sur la constante Python locale si LangFuse est
    injoignable ou mal configuré (voir backend.llm.gateway.prompt_loader
    pour la mécanique, partagée par tous les agents)."""
    fallback = _FALLBACKS.get(name)
    if fallback is None:
        raise ValueError(f"Prompt orchestrateur inconnu : {name!r}. Valides : {sorted(_FALLBACKS)}")
    return get_prompt(name, fallback, **variables)
