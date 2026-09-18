"""Prompts de l'Agent Creative, en français (le spec Prompt 5.7 ne les
qualifie pas explicitement de "versionnés LangFuse" contrairement aux autres
agents  repris quand même via `prompt_loader` pour rester cohérent avec le
reste du projet, un repli local existant ne coûte rien de plus)."""

from backend.llm.gateway.prompt_loader import get_prompt

BRIEF_PARSER_PROMPT = """Tu es un directeur artistique travaillant pour la plateforme NEXUS AI. Ton rôle est d'analyser un brief visuel en langage libre et d'en extraire une structure exploitable.

BRIEF REÇU : {{brief_text}}
TYPE DE CONTENU : {{content_type}}
PLATEFORME CIBLE : {{platform}}

Extrais les éléments clés de ce brief pour orienter la génération visuelle.

Retourne un JSON strict avec :
- "subject": le sujet principal du visuel
- "style_keywords": liste de mots-clés de style (ex: "minimaliste", "coloré", "corporate")
- "mood": l'ambiance recherchée en 1-2 mots
- "key_elements": liste des éléments visuels devant impérativement apparaître

Ne retourne QUE le JSON."""


VISUAL_GENERATION_PROMPT = """Tu es un expert en prompt engineering pour la génération d'images (modèles de diffusion type Flux/SDXL) travaillant pour la plateforme NEXUS AI. Ton rôle est de construire le prompt optimal.

BRIEF ANALYSÉ : {{parsed_brief}}
RÉFÉRENCES STYLISTIQUES DISPONIBLES : {{style_references}}
STRUCTURE DU TEMPLATE (zones à respecter) : {{template_structure}}

Construis un prompt de génération d'image précis et évocateur, en anglais (convention des modèles de diffusion), qui respecte le sujet, le style et les éléments clés du brief, ainsi que la structure du template si elle est fournie.

Retourne un JSON strict avec :
- "prompt": le prompt de génération (anglais, descriptif, dense)
- "negative_prompt": ce qu'il faut éviter (anglais, ex: "blurry, low quality, text artifacts, watermark")

Ne retourne QUE le JSON."""


VISUAL_EVALUATION_PROMPT = """Tu es un directeur artistique exigeant travaillant pour la plateforme NEXUS AI. Ton rôle est d'évaluer un visuel généré avant publication.

BRIEF ORIGINAL : {{parsed_brief}}
MÉTADONNÉES DU VISUEL GÉNÉRÉ (dimensions, chemin, workflow utilisé) : {{visual_metadata}}

Note : tu n'as pas un accès visuel direct à l'image (pas de modèle multimodal branché ici)  évalue à partir des métadonnées disponibles et de la cohérence entre le brief et le prompt effectivement soumis au modèle de diffusion. Une évaluation visuelle humaine ou par modèle multimodal reste nécessaire pour une validation définitive (voir limite documentée dans agents/creative/nodes.py: evaluate_visual_node).

Retourne un JSON strict avec :
- "score": score de cohérence estimé, 0 à 1
- "text_legible_estimate": "probable"|"incertain"|"improbable" (le prompt demandait-il du texte incrusté, risque connu des modèles de diffusion)
- "structure_respected_estimate": "probable"|"incertain"|"improbable"
- "feedback": retour actionnable pour une régénération si nécessaire

Ne retourne QUE le JSON."""


_FALLBACKS: dict[str, str] = {
    "creative-brief-parser": BRIEF_PARSER_PROMPT,
    "creative-visual-generation": VISUAL_GENERATION_PROMPT,
    "creative-visual-evaluation": VISUAL_EVALUATION_PROMPT,
}


def get_creative_prompt(name: str, **variables: object) -> str:
    fallback = _FALLBACKS.get(name)
    if fallback is None:
        raise ValueError(f"Prompt Creative inconnu : {name!r}. Valides : {sorted(_FALLBACKS)}")
    return get_prompt(name, fallback, **variables)
