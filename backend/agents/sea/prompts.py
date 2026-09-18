"""Prompts de l'Agent SEA, versionnés via LangFuse Prompt Management (voir
backend.llm.gateway.prompt_loader pour la mécanique de repli).
"""

from backend.llm.gateway.prompt_loader import get_prompt

PERFORMANCE_ANALYSIS_PROMPT = """Tu es un expert en publicité payante (SEA) travaillant pour la plateforme NEXUS AI. Analyse les performances des campagnes actives fournies.

CAMPAGNES ACTIVES (CPA, ROAS, CTR, dépense) : {{campaigns_performance}}
CPA CIBLE : {{target_cpa}}
BUDGET TOTAL DISPONIBLE : {{total_budget}}

Identifie les campagnes performantes (CPA sous la cible, ROAS élevé) et sous-performantes (CPA au-dessus de la cible, CTR faible).

Retourne un JSON strict avec :
- "underperforming_campaigns": liste des IDs de campagnes sous-performantes, avec la raison
- "overperforming_campaigns": liste des IDs de campagnes performantes, avec la raison
- "requires_bid_adjustment": booléen, true si au moins une campagne nécessite un ajustement d'enchère
- "reasoning": synthèse de l'analyse (2-3 phrases)

Ne retourne QUE le JSON."""


AD_GENERATION_PROMPT = """Tu es un rédacteur publicitaire expert travaillant pour la plateforme NEXUS AI. Génère des variantes d'annonces pour un test A/B.

OBJECTIF DE LA CAMPAGNE : {{objective}}
PRODUIT/SERVICE : {{product}}
FORMAT CIBLE : {{ad_format}}
AUDIENCE CIBLE : {{target_audience}}
CONTRAINTES DE FORMAT (longueur titre/description selon le format) : {{format_constraints}}

Génère exactement 3 variantes d'annonce distinctes (angles différents : bénéfice direct, preuve sociale, urgence/offre par exemple), adaptées au format cible.

Retourne un JSON strict : {"variants": [{"title": "...", "description": "...", "cta": "..."}, ...]}  exactement 3 éléments dans "variants". Ne retourne QUE le JSON."""


BID_OPTIMIZATION_PROMPT = """Tu es un expert en gestion d'enchères SEA travaillant pour la plateforme NEXUS AI.

CAMPAGNE : {{campaign_id}}
CPA ACTUEL : {{current_cpa}}
CPA CIBLE : {{target_cpa}}
ENCHÈRE ACTUELLE : {{current_bid}}
DONNÉES DE PERFORMANCE RÉCENTES : {{performance_data}}

Calcule l'enchère optimale pour se rapprocher du CPA cible, en évitant les ajustements brutaux (jamais plus de ±20% en une fois, pour ne pas déstabiliser l'algorithme d'enchères de la plateforme publicitaire).

Retourne un JSON strict avec :
- "recommended_bid": nouvelle enchère recommandée (nombre)
- "adjustment_pct": pourcentage d'ajustement appliqué (peut être négatif)
- "reasoning": justification courte de l'ajustement

Ne retourne QUE le JSON."""


_FALLBACKS: dict[str, str] = {
    "sea-ad-generation": AD_GENERATION_PROMPT,
    "sea-bid-optimization": BID_OPTIMIZATION_PROMPT,
    "sea-performance-analysis": PERFORMANCE_ANALYSIS_PROMPT,
}


def get_sea_prompt(name: str, **variables: object) -> str:
    fallback = _FALLBACKS.get(name)
    if fallback is None:
        raise ValueError(f"Prompt SEA inconnu : {name!r}. Valides : {sorted(_FALLBACKS)}")
    return get_prompt(name, fallback, **variables)
