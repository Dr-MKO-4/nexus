"""Adaptateur de contenu par plateforme sociale  Prompt 5.4.

Prend en entrée un `backend.core.state.state_models.Content` (produit par
l'Agent Content) et produit une structure adaptée aux contraintes de chaque
réseau.
"""

import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.core.state.state_models import Content

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

LINKEDIN_MAX_CHARS = 3000
# Au-delà de ce seuil, LinkedIn favorise le format "article" plutôt qu'un
# post texte classique (règle d'usage LinkedIn, pas une limite API stricte).
LINKEDIN_ARTICLE_THRESHOLD_CHARS = 1300
INSTAGRAM_MAX_CHARS = 2200
INSTAGRAM_MAX_HASHTAGS = 30
TWITTER_MAX_CHARS = 280


class LinkedInPost(BaseModel):
    model_config = _STRICT_CONFIG

    text: str
    hashtags: list[str]
    is_article_format: bool


class InstagramPost(BaseModel):
    model_config = _STRICT_CONFIG

    caption: str
    hashtags: list[str]
    optimal_image_ratio: str = "1:1"


class TikTokPost(BaseModel):
    model_config = _STRICT_CONFIG

    script: str
    hooks: list[str]
    trending_sounds_suggested: list[str] = Field(default_factory=list)


class Tweet(BaseModel):
    model_config = _STRICT_CONFIG

    text: str
    thread: list[str] = Field(default_factory=list)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _professional_hashtags(hashtags: list[str], limit: int = 5) -> list[str]:
    """LinkedIn valorise peu de hashtags, ciblés  au-delà de `limit`, le
    signal se dilue (convention d'usage LinkedIn)."""
    return hashtags[:limit]


def adapt_for_linkedin(content: Content) -> LinkedInPost:
    body = content.body or ""
    hashtags = _professional_hashtags(content.metadata.get("hashtags", []))
    is_article_format = len(body) > LINKEDIN_ARTICLE_THRESHOLD_CHARS
    text = body if is_article_format else _truncate(body, LINKEDIN_MAX_CHARS)
    logger.debug("content_adapter.linkedin", content_id=content.id, is_article_format=is_article_format)
    return LinkedInPost(text=text, hashtags=hashtags, is_article_format=is_article_format)


def adapt_for_instagram(content: Content) -> InstagramPost:
    body = content.body or ""
    hashtags = content.metadata.get("hashtags", [])[:INSTAGRAM_MAX_HASHTAGS]
    caption = _truncate(body, INSTAGRAM_MAX_CHARS)
    logger.debug("content_adapter.instagram", content_id=content.id, hashtag_count=len(hashtags))
    return InstagramPost(caption=caption, hashtags=hashtags)


# Aucun outil de veille des sons tendance TikTok réel n'existe dans ce
# projet (contrairement à SearXNG pour la veille texte)  une intégration à
# l'API TikTok Creative Center serait nécessaire pour des suggestions
# réellement à jour. En attendant, ces catégories génériques (choisies selon
# le ton du contenu) donnent une suggestion exploitable plutôt qu'une liste
# vide, tout en étant honnêtement documentées comme un repli heuristique.
_TRENDING_SOUND_CATEGORIES: dict[str, list[str]] = {
    "energetic": ["son percutant/upbeat tendance (à vérifier sur TikTok Creative Center)"],
    "emotional": ["musique douce/inspirante tendance (à vérifier sur TikTok Creative Center)"],
    "informative": ["voix off claire sur son de fond discret tendance (à vérifier sur TikTok Creative Center)"],
}
_ENERGETIC_WORDS = ("lancement", "nouveau", "découvrez", "offre", "promo", "boostez", "explosif")
_EMOTIONAL_WORDS = ("merci", "histoire", "témoignage", "communauté", "ensemble", "fier", "fiers")


def _suggest_trending_sound_category(text: str) -> str:
    lowered = text.lower()
    if any(w in lowered for w in _ENERGETIC_WORDS):
        return "energetic"
    if any(w in lowered for w in _EMOTIONAL_WORDS):
        return "emotional"
    return "informative"


def adapt_for_tiktok(content: Content) -> TikTokPost:
    body = content.body or ""
    first_sentence = body.split(".")[0].strip() if body else (content.title or "")
    hooks = [h for h in [first_sentence, content.title] if h]
    # Script condensé : le titre comme accroche, un extrait court du corps 
    # un vrai script vidéo (voix off complète) relève de l'Agent Créatif
    # (Prompt 5.7), pas de l'Agent Social qui adapte du texte existant.
    script = f"{content.title or ''}\n\n{_truncate(body, 500)}".strip()
    category = _suggest_trending_sound_category(f"{content.title or ''} {body}")
    logger.debug("content_adapter.tiktok", content_id=content.id, sound_category=category)
    return TikTokPost(script=script, hooks=hooks, trending_sounds_suggested=_TRENDING_SOUND_CATEGORIES[category])


def adapt_for_twitter(content: Content) -> Tweet:
    body = content.body or ""
    if len(body) <= TWITTER_MAX_CHARS:
        return Tweet(text=body, thread=[])

    words = body.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > TWITTER_MAX_CHARS - 6:  # marge pour le suffixe "(n/N)"
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)

    total = len(chunks)
    thread = [f"{chunk} ({i + 1}/{total})" for i, chunk in enumerate(chunks)]
    logger.debug("content_adapter.twitter_thread", content_id=content.id, chunk_count=total)
    return Tweet(text=thread[0], thread=thread[1:])


__all__ = [
    "LinkedInPost",
    "InstagramPost",
    "TikTokPost",
    "Tweet",
    "adapt_for_linkedin",
    "adapt_for_instagram",
    "adapt_for_tiktok",
    "adapt_for_twitter",
]
