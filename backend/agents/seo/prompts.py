"""Prompts de l'Agent SEO, versionnés via LangFuse Prompt Management (voir
backend.llm.gateway.prompt_loader pour la mécanique de repli).
"""

from backend.llm.gateway.prompt_loader import get_prompt

KEYWORD_RESEARCH_PROMPT = """Tu es un expert SEO travaillant pour la plateforme NEXUS AI. Ton rôle est d'identifier des opportunités de mots-clés pertinentes pour l'objectif business fourni.

OBJECTIF : {{objective}}
SECTEUR D'ACTIVITÉ : {{industry}}
MOTS-CLÉS DÉJÀ SUIVIS (à ne pas dupliquer) : {{existing_keywords}}
CANDIDATS COLLECTÉS (Serper/SearXNG, avec intention et difficulté estimée) : {{keyword_candidates}}

Sélectionne parmi les candidats ceux qui représentent la meilleure opportunité : un équilibre entre volume de recherche suffisant, difficulté raisonnable compte tenu de la maturité SEO du client, et alignement clair avec l'objectif business.

Retourne un JSON strict : {"selected_keywords": [{"term": "...", "reasoning": "..."}]}  "reasoning" explique en une phrase pourquoi ce mot-clé est une bonne opportunité. Ne retourne QUE le JSON."""


BRIEF_GENERATION_PROMPT = """Tu es un expert SEO rédigeant un brief de contenu à destination de l'Agent Content de NEXUS AI.

MOT-CLÉ CIBLE : {{keyword}}
CLUSTER DE MOTS-CLÉS ASSOCIÉS : {{cluster_keywords}}
INTENTION DE RECHERCHE : {{intent}}
LIGNE ÉDITORIALE DU CLIENT : {{editorial_guidelines}}

Produis un brief de contenu complet et actionnable. Retourne un JSON strict avec :
- "title": titre proposé, optimisé SEO (contient le mot-clé cible, moins de 60 caractères)
- "structure": liste ordonnée des sections (H2/H3) à couvrir
- "target_keywords": mots-clés à intégrer naturellement dans le contenu (cible + cluster)
- "target_length_words": longueur cible en nombre de mots, cohérente avec l'intention de recherche
- "editorial_angle": l'angle éditorial à adopter (1-2 phrases)

Ne retourne QUE le JSON."""


COMPETITOR_ANALYSIS_PROMPT = """Tu es un expert SEO analysant la concurrence sur les SERP pour la plateforme NEXUS AI.

MOT-CLÉ : {{keyword}}
RÉSULTATS SERP COLLECTÉS (titres, URLs, extraits des concurrents en tête) : {{serp_results}}

Analyse ce que les pages les mieux positionnées ont en commun (format de contenu, angle, longueur apparente, éléments distinctifs) et identifie les opportunités de différenciation.

Retourne un JSON strict avec :
- "common_patterns": ce que partagent les résultats en tête (liste de constats courts)
- "content_gaps": angles ou sous-sujets absents des résultats actuels, à exploiter
- "recommended_format": format de contenu recommandé pour concurrencer efficacement

Ne retourne QUE le JSON."""


_FALLBACKS: dict[str, str] = {
    "seo-keyword-research": KEYWORD_RESEARCH_PROMPT,
    "seo-brief-generation": BRIEF_GENERATION_PROMPT,
    "seo-competitor-analysis": COMPETITOR_ANALYSIS_PROMPT,
}


def get_seo_prompt(name: str, **variables: object) -> str:
    fallback = _FALLBACKS.get(name)
    if fallback is None:
        raise ValueError(f"Prompt SEO inconnu : {name!r}. Valides : {sorted(_FALLBACKS)}")
    return get_prompt(name, fallback, **variables)
