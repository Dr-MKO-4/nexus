"""Évaluateurs de qualité automatiques  Prompt 6.2.

`evaluate_content_quality`/`evaluate_ad_copy` : LLM-as-judge (task_type=
"classification" -> Mistral 7B, voir hybrid_router.TASK_TYPE_TO_LOCAL_MODEL 
cohérent avec la demande explicite du spec pour `evaluate_content_quality`,
étendue à `evaluate_ad_copy` par cohérence, aucune méthode alternative
n'étant précisée pour cette dernière). `evaluate_email_subject` est une
heuristique déterministe (le spec énumère explicitement ses critères 
longueur/personnalisation/urgence/clarté  sans mentionner de LLM,
contrairement aux deux autres).

"Évaluations déclenchées automatiquement après chaque génération" (spec) :
CE FICHIER fournit les fonctions d'évaluation elles-mêmes ; leur câblage
DANS les nœuds de génération existants (`agents/content/nodes.py:
generate_draft_node`, `agents/email/nodes.py: generate_email_content_node`,
`agents/sea/nodes.py: generate_ad_variants_node`...) n'est PAS fait ici 
hors du périmètre de fichiers listés par ce prompt (seul `core/monitoring/
evaluators.py` est demandé, pas de modification des fichiers agents
existants). Point d'intégration documenté, pas un oubli silencieux."""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

_JUDGE_TASK_TYPE = "classification"  # -> Mistral 7B, voir hybrid_router.py


async def _llm_judge_score(prompt: str, agent_name: str) -> float:
    """Appel LLM-as-judge partagé par `evaluate_content_quality`/
    `evaluate_ad_copy`  retourne 0.0 en cas d'échec (LLM indisponible,
    sortie non conforme) plutôt que de lever, une évaluation automatique ne
    doit jamais faire échouer le pipeline de génération qu'elle observe."""
    try:
        from pydantic import BaseModel, ConfigDict, Field

        from backend.llm.gateway.llm_client import NexusLLMClient

        class _JudgeScore(BaseModel):
            model_config = ConfigDict(extra="forbid")
            score: float = Field(ge=0, le=1)

        llm_client = NexusLLMClient()
        result = await llm_client.complete_structured(
            prompt=prompt, response_model=_JudgeScore, task_type=_JUDGE_TASK_TYPE, agent_name=agent_name
        )
        return result.score
    except Exception as exc:
        logger.warning("evaluators.llm_judge_failed", agent_name=agent_name, error=str(exc))
        return 0.0


async def evaluate_content_quality(content: str, target_keywords: list[str]) -> float:
    """LLM-as-judge (Mistral 7B) : cohérence, pertinence par rapport aux
    mots-clés cibles, qualité rédactionnelle. Score 0-1."""
    keywords_text = ", ".join(target_keywords) or "aucun"
    prompt = f"""Tu es un rédacteur en chef évaluant la qualité d'un contenu marketing.

CONTENU : {content[:3000]}
MOTS-CLÉS CIBLES : {keywords_text}

Évalue la qualité globale de ce contenu (cohérence, pertinence par rapport aux mots-clés, qualité rédactionnelle).

Retourne un JSON strict avec :
- "score": note de 0 (mauvais) à 1 (excellent)

Ne retourne QUE le JSON."""
    score = await _llm_judge_score(prompt, agent_name="evaluator_content_quality")
    logger.info("evaluators.content_quality_evaluated", score=score)
    return score


_URGENCY_WORDS = ("maintenant", "aujourd'hui", "derniere chance", "offre limitee", "urgent", "vite", "depechez")
_PERSONALIZATION_TOKENS = ("{prenom}", "{firstname}", "{contactfield=firstname}", "{nom}")
_OPTIMAL_SUBJECT_LENGTH_RANGE = (30, 60)  # caractères  bonne lisibilité mobile


def _strip_accents(text: str) -> str:
    """Normalise les accents (NFD + suppression des marques combinantes) 
    le français courant (et a fortiori un texte généré par LLM ou saisi par
    un opérateur) ne garantit aucune cohérence d'accentuation ("derniere" vs
    "dernière") ; un matching de mots-clés sensible aux accents raterait
    silencieusement des correspondances légitimes (vérifié : c'est
    exactement ce qui s'est produit en testant ce module avant ce correctif
     "derniere chance" sans accent ne matchait pas "dernière chance")."""
    import unicodedata

    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def evaluate_email_subject(subject: str) -> float:
    """Heuristique déterministe (spec : longueur, personnalisation, urgence,
    clarté)  pas de LLM, contrairement à `evaluate_content_quality`.
    Chaque critère contribue 0.25 au score final (poids égal, non précisé
    autrement par le spec)."""
    if not subject or not subject.strip():
        return 0.0

    length = len(subject)
    min_len, max_len = _OPTIMAL_SUBJECT_LENGTH_RANGE
    if min_len <= length <= max_len:
        length_score = 1.0
    else:
        distance = min_len - length if length < min_len else length - max_len
        length_score = max(0.0, 1.0 - distance / max_len)

    lowered = _strip_accents(subject.lower())
    personalization_score = 1.0 if any(token in lowered for token in _PERSONALIZATION_TOKENS) else 0.0
    urgency_score = 1.0 if any(word in lowered for word in _URGENCY_WORDS) else 0.0

    # Clarté : approximée par l'absence de ponctuation excessive/majuscules
    # criardes (signaux de spam plutôt que de clarté) et un nombre de mots
    # raisonnable (3-10).
    word_count = len(subject.split())
    excessive_punctuation = bool(re.search(r"[!?]{2,}", subject))
    excessive_caps = sum(1 for c in subject if c.isupper()) > len(subject) * 0.5
    clarity_score = 1.0 if (3 <= word_count <= 10 and not excessive_punctuation and not excessive_caps) else 0.5

    score = (length_score + personalization_score + urgency_score + clarity_score) / 4
    logger.info(
        "evaluators.email_subject_evaluated",
        score=score,
        length_score=length_score,
        personalization_score=personalization_score,
        urgency_score=urgency_score,
        clarity_score=clarity_score,
    )
    return score


async def evaluate_ad_copy(ad_text: str, target_audience: str) -> float:
    """LLM-as-judge (Mistral 7B) : pertinence du texte publicitaire par
    rapport à l'audience cible. Score 0-1."""
    prompt = f"""Tu es un expert en copywriting publicitaire évaluant un texte d'annonce.

TEXTE DE L'ANNONCE : {ad_text[:1000]}
AUDIENCE CIBLE : {target_audience}

Évalue si ce texte est susceptible de capter l'attention et de convertir cette audience spécifique.

Retourne un JSON strict avec :
- "score": note de 0 (inefficace) à 1 (excellent)

Ne retourne QUE le JSON."""
    score = await _llm_judge_score(prompt, agent_name="evaluator_ad_copy")
    logger.info("evaluators.ad_copy_evaluated", score=score)
    return score


async def send_evaluation_to_langfuse(trace_id: str, evaluator_name: str, score: float) -> None:
    """Envoie le score d'un évaluateur à LangFuse  réutilise
    `NexusTracer.score_trace` plutôt que de dupliquer l'appel
    `create_score`."""
    from backend.core.monitoring.langfuse_tracer import NexusTracer

    NexusTracer().score_trace(trace_id, evaluator_name, score)


__all__ = ["evaluate_content_quality", "evaluate_email_subject", "evaluate_ad_copy", "send_evaluation_to_langfuse"]
