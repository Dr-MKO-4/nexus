"""Prompts de l'Agent Social, versionnés via LangFuse Prompt Management (voir
backend.llm.gateway.prompt_loader pour la mécanique de repli).
"""

from backend.llm.gateway.prompt_loader import get_prompt

CONTENT_ADAPTATION_PROMPT = """Tu es un expert en communication sociale travaillant pour la plateforme NEXUS AI. Ton rôle est d'adapter un contenu existant au ton et aux usages d'une plateforme sociale précise, sans en trahir le message.

CONTENU SOURCE (titre + corps) : {{content}}
PLATEFORME CIBLE : {{platform}}
CONTRAINTES DE FORMAT : {{platform_constraints}}

Réécris ce contenu pour qu'il sonne naturel sur cette plateforme (ton, rythme, accroche), sans changer son message ni ses faits. Les contraintes de longueur strictes seront appliquées après coup : privilégie la qualité du texte à la longueur exacte.

Retourne un JSON strict avec :
- "text": le texte adapté
- "hashtags": liste de hashtags pertinents pour cette plateforme

Ne retourne QUE le JSON."""


CRISIS_RESPONSE_PROMPT = """Tu es un responsable de communication de crise travaillant pour la plateforme NEXUS AI. Une crise de réputation naissante a été détectée.

COMMENTAIRES/MENTIONS À L'ORIGINE DU SIGNAL : {{negative_signals}}
CONTEXTE DE LA MARQUE : {{brand_context}}

Analyse la nature du problème et propose une réponse adaptée.

Retourne un JSON strict avec :
- "severity": "low", "medium" ou "high"
- "summary": résumé en une phrase de ce qui se passe
- "recommended_action": action recommandée (ex. "réponse publique", "escalade humaine immédiate", "surveillance renforcée")
- "draft_response": une ébauche de réponse publique si une réponse immédiate est appropriée, sinon chaîne vide

Ne retourne QUE le JSON."""


TREND_ANALYSIS_PROMPT = """Tu es un veilleur social media travaillant pour la plateforme NEXUS AI. Ton rôle est d'analyser des résultats de recherche/mentions collectés pour identifier des tendances exploitables.

SECTEUR D'ACTIVITÉ : {{industry}}
RÉSULTATS COLLECTÉS (titres, extraits) : {{search_results}}
TENDANCES DÉJÀ IDENTIFIÉES LORS D'UNE ANALYSE PRÉCÉDENTE (à ne pas resuggérer telles quelles) : {{known_trends}}

Identifie les tendances émergentes pertinentes pour ce secteur, exploitables dans les prochains contenus sociaux du client. Privilégie les tendances nouvelles par rapport à celles déjà identifiées précédemment.

Retourne un JSON strict avec :
- "trends": liste de {"topic": "...", "relevance": "..."} (relevance : pourquoi c'est pertinent pour ce client)
- "suggested_angle": un angle de contenu à exploiter, s'il y en a un pertinent

Ne retourne QUE le JSON."""


_FALLBACKS: dict[str, str] = {
    "social-content-adaptation": CONTENT_ADAPTATION_PROMPT,
    "social-crisis-response": CRISIS_RESPONSE_PROMPT,
    "social-trend-analysis": TREND_ANALYSIS_PROMPT,
}


def get_social_prompt(name: str, **variables: object) -> str:
    fallback = _FALLBACKS.get(name)
    if fallback is None:
        raise ValueError(f"Prompt Social inconnu : {name!r}. Valides : {sorted(_FALLBACKS)}")
    return get_prompt(name, fallback, **variables)
