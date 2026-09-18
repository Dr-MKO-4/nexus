"""Gestionnaire de prompts via LangFuse Prompt Management  Prompt 6.2.

Relation avec `backend.llm.gateway.prompt_loader` (Prompt 3.1, déjà
existant) : `prompt_loader.get_prompt(name, fallback, **variables)` est le
chemin CHAUD, utilisé par chaque `agents/<nom>/prompts.py` à chaque appel
d'agent  récupération + interpolation, optimisé pour être appelé souvent.
Ce module (`prompt_manager.py`) est la couche de GESTION (créer/mettre à
jour/lister des prompts), un usage plus rare (admin/ops), avec son propre
cache local TTL 5 min distinct de celui de LangFuse lui-même  les deux
coexistent sciemment, pas une duplication accidentelle. `get_prompt` ici
retourne le TEXTE déjà résolu (comme `prompt_loader`), sans interpolation de
variables (absente de la signature imposée par le spec :
`get_prompt(name, version=None) → str`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)
_CACHE_TTL_SECONDS = 5 * 60


class PromptInfo(BaseModel):
    model_config = _STRICT_CONFIG

    name: str
    version: int
    labels: list[str] = []
    tags: list[str] = []


@dataclass
class _CacheEntry:
    text: str
    expires_at: float


_local_cache: dict[str, _CacheEntry] = {}


def _safe_client():
    try:
        from backend.config.logging import get_langfuse_client

        return get_langfuse_client()
    except Exception as exc:
        logger.debug("prompt_manager.client_unavailable", error=str(exc))
        return None


def _cache_key(name: str, version: int | None) -> str:
    return f"{name}:{version if version is not None else 'latest'}"


def get_prompt(name: str, version: int | None = None) -> str | None:
    """Récupère le texte d'un prompt (cache local TTL 5 min en premier,
    puis LangFuse). Retourne `None` si introuvable ET LangFuse indisponible
     PAS de repli sur un prompt local générique ici (contrairement à
    `prompt_loader.get_prompt`, qui EXIGE un `fallback` explicite fourni par
    l'appelant à chaque fois) : ce module gère des prompts par nom seul,
    sans qu'un fallback candidat soit connu à cet endroit générique."""
    key = _cache_key(name, version)
    cached = _local_cache.get(key)
    if cached is not None and cached.expires_at > time.monotonic():
        logger.debug("prompt_manager.cache_hit", name=name, version=version)
        return cached.text

    client = _safe_client()
    if client is None:
        return None

    try:
        prompt_client = client.get_prompt(name, version=version, type="text")
        text = prompt_client.prompt
    except Exception as exc:
        logger.warning("prompt_manager.get_prompt_failed", name=name, version=version, error=str(exc))
        return None

    _local_cache[key] = _CacheEntry(text=text, expires_at=time.monotonic() + _CACHE_TTL_SECONDS)
    return text


def update_prompt(name: str, content: str, tags: list[str] | None = None) -> str | None:
    """Crée une NOUVELLE VERSION du prompt `name` (LangFuse versionne les
    prompts par incrément, il n'y a pas de "mise à jour en place"  voir
    `client.create_prompt`). Retourne un identifiant `"{name}:{version}"`
    (LangFuse n'a pas de `prompt_id` opaque séparé du couple
    nom+version  vérifié par inspection du type de retour de
    `create_prompt`, qui n'expose que `name`/`version`, pas d'id)."""
    client = _safe_client()
    if client is None:
        return None

    try:
        prompt_client = client.create_prompt(name=name, prompt=content, tags=tags, type="text")
    except Exception as exc:
        logger.warning("prompt_manager.update_prompt_failed", name=name, error=str(exc))
        return None

    prompt_id = f"{prompt_client.name}:{prompt_client.version}"
    # Invalide le cache local de CE nom (toutes versions) : une nouvelle
    # version vient d'être créée, un prochain get_prompt(name) sans version
    # explicite doit la voir plutôt que de servir l'ancienne jusqu'à
    # expiration du TTL.
    stale_keys = [k for k in _local_cache if k.startswith(f"{name}:")]
    for k in stale_keys:
        del _local_cache[k]

    logger.info("prompt_manager.prompt_updated", name=name, version=prompt_client.version)
    return prompt_id


def list_prompts() -> list[PromptInfo]:
    """Liste les prompts disponibles via l'API REST LangFuse
    (`client.api.prompts.list()`)  pas de méthode dédiée sur le SDK client
    Python lui-même pour cette opération (vérifié : absente de la liste des
    méthodes du client). Non re-vérifié contre un vrai serveur LangFuse
    authentifié dans ce sandbox (aucune instance disponible)  la forme de
    la réponse est basée sur la documentation REST LangFuse (`GET /api/
    public/v2/prompts`), à confirmer avant un usage en production."""
    client = _safe_client()
    if client is None:
        return []

    try:
        response = client.api.prompts.list()
        items: Any = getattr(response, "data", response)
    except Exception as exc:
        logger.warning("prompt_manager.list_prompts_failed", error=str(exc))
        return []

    prompts: list[PromptInfo] = []
    for item in items or []:
        try:
            prompts.append(
                PromptInfo(
                    name=item.name,
                    version=item.version,
                    labels=list(getattr(item, "labels", []) or []),
                    tags=list(getattr(item, "tags", []) or []),
                )
            )
        except Exception as exc:
            logger.debug("prompt_manager.list_prompts_item_skipped", error=str(exc))

    return prompts


__all__ = ["PromptInfo", "get_prompt", "update_prompt", "list_prompts"]
