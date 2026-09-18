"""Prompts de l'Agent Reporting, versionnés via LangFuse Prompt Management
(voir backend.llm.gateway.prompt_loader pour la mécanique de repli).

Chaque prompt impose explicitement : format professionnel/actionnable/chiffré,
ton direct sans jargon technique excessif (spec Prompt 5.8).
"""

from backend.llm.gateway.prompt_loader import get_prompt

_FORMAT_INSTRUCTIONS = """CONSIGNES DE FORMAT ET DE TON (impératives) :
- Professionnel et actionnable : chaque affirmation doit s'appuyer sur un chiffre concret, jamais une généralité vague.
- Chiffré : cite systématiquement les valeurs (KPIs, pourcentages, montants) plutôt que des qualificatifs seuls ("en hausse" -> "+23%").
- Ton direct, sans jargon technique excessif : ce rapport est lu par des décideurs marketing, pas des ingénieurs  évite les termes internes aux agents (noms de modèles, de pipelines, etc.)."""


EXECUTIVE_SUMMARY_PROMPT = f"""Tu es un directeur marketing rédigeant le résumé exécutif du rapport hebdomadaire pour la plateforme NEXUS AI.

PÉRIODE : {{{{period}}}}
KPIS DE LA SEMAINE : {{{{kpis}}}}
ANOMALIES DÉTECTÉES : {{{{anomalies}}}}
DÉCISIONS PRISES PAR LES AGENTS CETTE SEMAINE : {{{{decisions}}}}

Rédige un résumé exécutif de 4 à 6 phrases : ce qui s'est passé cette semaine, ce qui mérite l'attention du client, la tendance générale.

{_FORMAT_INSTRUCTIONS}

Retourne un JSON strict avec :
- "executive_summary": le résumé (texte)

Ne retourne QUE le JSON."""


CHANNEL_ANALYSIS_PROMPT = f"""Tu es un analyste marketing cross-canal rédigeant l'analyse détaillée par canal du rapport hebdomadaire pour la plateforme NEXUS AI.

KPIS PAR CANAL : {{{{channel_kpis}}}}
ATTRIBUTION MULTI-TOUCH : {{{{attribution}}}}

Pour chaque canal disponible dans les données, rédige une analyse courte de sa performance et de son évolution.

{_FORMAT_INSTRUCTIONS}

Retourne un JSON strict avec :
- "channels": liste de {{"channel": "...", "summary": "..."}}

Ne retourne QUE le JSON."""


RECOMMENDATIONS_PROMPT = f"""Tu es un consultant marketing rédigeant les recommandations pour la semaine suivante, dans le rapport hebdomadaire de la plateforme NEXUS AI.

RÉSUMÉ EXÉCUTIF : {{{{executive_summary}}}}
ANALYSE PAR CANAL : {{{{channel_breakdown}}}}
ANOMALIES : {{{{anomalies}}}}

Propose des recommandations actionnables pour la semaine suivante, ainsi qu'un court plan pour la semaine suivante.

{_FORMAT_INSTRUCTIONS}

Retourne un JSON strict avec :
- "recommendations": liste de {{"action": "...", "expected_impact": "...", "effort": "low"|"medium"|"high", "priority": 1 à 5 (1 = le plus prioritaire)}}
- "next_week_plan": plan court pour la semaine suivante (2-3 phrases)

Ne retourne QUE le JSON."""


_FALLBACKS: dict[str, str] = {
    "reporting-executive-summary": EXECUTIVE_SUMMARY_PROMPT,
    "reporting-channel-analysis": CHANNEL_ANALYSIS_PROMPT,
    "reporting-recommendations": RECOMMENDATIONS_PROMPT,
}


def get_reporting_prompt(name: str, **variables: object) -> str:
    fallback = _FALLBACKS.get(name)
    if fallback is None:
        raise ValueError(f"Prompt Reporting inconnu : {name!r}. Valides : {sorted(_FALLBACKS)}")
    return get_prompt(name, fallback, **variables)
