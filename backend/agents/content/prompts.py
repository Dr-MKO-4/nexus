"""Prompts de l'Agent Content, versionnés via LangFuse Prompt Management (voir
backend.llm.gateway.prompt_loader pour la mécanique de repli).
"""

from backend.llm.gateway.prompt_loader import get_prompt

_OUTPUT_CONTRACT = """Retourne un JSON strict avec :
- "title": titre du contenu
- "body": corps du contenu (texte complet)
- "meta_description": méta-description SEO (155 caractères max)
- "hashtags": liste de hashtags pertinents (peut être vide selon le format)

Ne retourne QUE le JSON."""


ARTICLE_GENERATION_PROMPT = f"""Tu es un rédacteur expert travaillant pour la plateforme NEXUS AI. Ton rôle est de rédiger un article optimisé SEO et fidèle à la ligne éditoriale du client.

BRIEF : {{{{brief}}}}
MOTS-CLÉS CIBLES : {{{{keywords}}}}
LIGNE ÉDITORIALE (ton, style, contraintes) : {{{{guidelines}}}}
CONTENUS SIMILAIRES DÉJÀ PUBLIÉS (à ne pas dupliquer, à différencier) : {{{{similar_contents}}}}
RETOUR D'ÉVALUATION DE LA VERSION PRÉCÉDENTE (le cas échéant, à corriger impérativement) : {{{{evaluation_feedback}}}}

Rédige un article complet, structuré (sous-titres inclus dans le corps), intégrant naturellement les mots-clés cibles et respectant strictement la ligne éditoriale.

{_OUTPUT_CONTRACT}"""


POST_SOCIAL_GENERATION_PROMPT = f"""Tu es un rédacteur social media expert travaillant pour la plateforme NEXUS AI. Ton rôle est de rédiger un post adapté à la plateforme ciblée.

BRIEF : {{{{brief}}}}
PLATEFORME : {{{{platform}}}}
CONTRAINTES DE FORMAT DE LA PLATEFORME : {{{{platform_constraints}}}}
LIGNE ÉDITORIALE (ton, style, contraintes) : {{{{guidelines}}}}
RETOUR D'ÉVALUATION DE LA VERSION PRÉCÉDENTE (le cas échéant, à corriger impérativement) : {{{{evaluation_feedback}}}}

Rédige un post percutant, adapté au format et aux usages de la plateforme ciblée.

{_OUTPUT_CONTRACT}"""


EMAIL_BODY_GENERATION_PROMPT = f"""Tu es un rédacteur email marketing expert travaillant pour la plateforme NEXUS AI. Ton rôle est de rédiger le corps d'un email.

BRIEF : {{{{brief}}}}
SEGMENT CIBLE : {{{{target_audience}}}}
LIGNE ÉDITORIALE (ton, style, contraintes) : {{{{guidelines}}}}
RETOUR D'ÉVALUATION DE LA VERSION PRÉCÉDENTE (le cas échéant, à corriger impérativement) : {{{{evaluation_feedback}}}}

Rédige un corps d'email clair, engageant, avec un appel à l'action explicite.

{_OUTPUT_CONTRACT}"""


LANDING_PAGE_GENERATION_PROMPT = f"""Tu es un rédacteur expert en pages de conversion travaillant pour la plateforme NEXUS AI. Ton rôle est de rédiger le contenu d'une landing page.

BRIEF : {{{{brief}}}}
MOTS-CLÉS CIBLES : {{{{keywords}}}}
LIGNE ÉDITORIALE (ton, style, contraintes) : {{{{guidelines}}}}
RETOUR D'ÉVALUATION DE LA VERSION PRÉCÉDENTE (le cas échéant, à corriger impérativement) : {{{{evaluation_feedback}}}}

Rédige le contenu complet de la landing page (accroche, bénéfices, preuve sociale, appel à l'action), optimisé pour la conversion et le SEO.

{_OUTPUT_CONTRACT}"""


CONTENT_EVALUATION_PROMPT = """Tu es un rédacteur en chef exigeant travaillant pour la plateforme NEXUS AI. Ton rôle est d'évaluer un contenu produit par l'Agent Content avant publication.

CONTENU À ÉVALUER : {{draft}}
LIGNE ÉDITORIALE (ton, style, contraintes) : {{guidelines}}
SCORE PYTORCH (qualité globale, SEO, lisibilité, engagement  0 à 1) : {{pytorch_score}}

Évalue le contenu sur le SEO, le ton, et la pertinence par rapport au brief et à la ligne éditoriale. Sois exigeant : signale tout écart de ton, toute maladresse, tout manque de pertinence.

Retourne un JSON strict avec :
- "score": ton évaluation globale, de 0 à 1 (peut différer du score PyTorch si tu détectes un problème qu'il ne capture pas)
- "feedback": retour actionnable, précis, à injecter dans la prochaine génération si le contenu doit être corrigé
- "tone_ok": booléen, le ton respecte-t-il la ligne éditoriale ?
- "relevance_ok": booléen, le contenu répond-il bien au brief ?

Ne retourne QUE le JSON."""


_FALLBACKS: dict[str, str] = {
    "content-article-generation": ARTICLE_GENERATION_PROMPT,
    "content-post-social-generation": POST_SOCIAL_GENERATION_PROMPT,
    "content-email-body-generation": EMAIL_BODY_GENERATION_PROMPT,
    "content-landing-page-generation": LANDING_PAGE_GENERATION_PROMPT,
    "content-evaluation": CONTENT_EVALUATION_PROMPT,
}


def get_content_prompt(name: str, **variables: object) -> str:
    fallback = _FALLBACKS.get(name)
    if fallback is None:
        raise ValueError(f"Prompt Content inconnu : {name!r}. Valides : {sorted(_FALLBACKS)}")
    return get_prompt(name, fallback, **variables)
