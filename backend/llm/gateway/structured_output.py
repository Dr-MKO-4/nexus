"""Parsing tolérant des réponses LLM censées être du JSON structuré.

Utilisé par les agents demandant une sortie JSON via prompt texte (par
opposition à `NexusLLMClient.complete_structured`/instructor, réservé aux
cas où le schéma de sortie est fixe et modélisable en Pydantic à l'avance).
Partagé pour éviter de dupliquer cette logique dans chaque agents/<nom>/nodes.py.
"""

import json
import re

import structlog

logger = structlog.get_logger(__name__)

_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def parse_llm_json(raw_response: str, *, source: str) -> tuple[dict, str | None]:
    """Tolère les blocs ```json``` que certains modèles ajoutent malgré la
    consigne "ne retourne QUE le JSON". Ne lève jamais : un JSON illisible
    retourne un dict vide + un message d'erreur (au lieu d'une exception) 
    à l'appelant de décider comment le signaler (Alert, log, etc.)."""
    candidate = raw_response.strip()
    fence_match = _JSON_FENCE_PATTERN.search(candidate)
    if fence_match:
        candidate = fence_match.group(1)
    else:
        object_match = _JSON_OBJECT_PATTERN.search(candidate)
        if object_match:
            candidate = object_match.group(0)

    try:
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("La réponse JSON n'est pas un objet.")
        return parsed, None
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("structured_output.parse_failed", source=source, error=str(exc), raw=raw_response[:500])
        return {}, f"Réponse LLM illisible en JSON pour {source} : {exc}"
