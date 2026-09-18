"""Prompts de l'Agent Analytics, versionnés via LangFuse Prompt Management (voir
backend.llm.gateway.prompt_loader pour la mécanique de repli).
"""

from backend.llm.gateway.prompt_loader import get_prompt

INSIGHT_GENERATION_PROMPT = """Tu es un analyste marketing expert travaillant pour la plateforme NEXUS AI. Ton rôle est de transformer des KPIs bruts en insights actionnables.

KPIS DE LA PÉRIODE : {{kpis}}
ANOMALIES DÉTECTÉES : {{anomalies}}
CONTEXTE HISTORIQUE (périodes précédentes) : {{contexte_historique}}

Identifie ce qui mérite l'attention du client : tendances significatives, écarts par rapport à l'historique, signaux faibles à surveiller. Priorise la clarté et l'actionnabilité sur l'exhaustivité.

Retourne un JSON strict avec :
- "insights": liste de {"summary": "...", "priority": "low"|"medium"|"high", "supporting_kpi": "..."}

Ne retourne QUE le JSON."""


RECOMMENDATION_PROMPT = """Tu es un consultant marketing expert travaillant pour la plateforme NEXUS AI. Ton rôle est de transformer des insights en recommandations concrètes et priorisées.

INSIGHTS : {{insights}}
KPIS DE LA PÉRIODE : {{kpis}}
BUDGET DISPONIBLE : {{budget}}

Propose des actions concrètes, réalisables avec le budget disponible, classées par impact attendu.

Retourne un JSON strict avec :
- "recommendations": liste de {"action": "...", "expected_impact": "...", "effort": "low"|"medium"|"high"}

Ne retourne QUE le JSON."""


ANOMALY_EXPLANATION_PROMPT = """Tu es un analyste marketing expert travaillant pour la plateforme NEXUS AI. Ton rôle est d'expliquer en langage clair une anomalie détectée statistiquement.

ANOMALIE DÉTECTÉE (score de reconstruction, explication technique) : {{anomaly}}
KPIS DE LA PÉRIODE : {{kpis}}
CONTEXTE HISTORIQUE : {{contexte_historique}}

Explique en langage clair, sans jargon statistique, ce que cette anomalie signifie probablement pour le business, et si elle appelle une action immédiate.

Retourne un JSON strict avec :
- "explanation": explication en langage clair (2-3 phrases)
- "requires_immediate_action": booléen

Ne retourne QUE le JSON."""


_FALLBACKS: dict[str, str] = {
    "analytics-insight-generation": INSIGHT_GENERATION_PROMPT,
    "analytics-recommendation": RECOMMENDATION_PROMPT,
    "analytics-anomaly-explanation": ANOMALY_EXPLANATION_PROMPT,
}


def get_analytics_prompt(name: str, **variables: object) -> str:
    fallback = _FALLBACKS.get(name)
    if fallback is None:
        raise ValueError(f"Prompt Analytics inconnu : {name!r}. Valides : {sorted(_FALLBACKS)}")
    return get_prompt(name, fallback, **variables)
