"""Outil de recherche de mots-clés multi-source : Serper API en priorité
(settings.SERPER_API_KEY), SearXNG self-hosted en repli gratuit.
"""

import re
from collections import defaultdict
from typing import Literal

import httpx
import structlog
from pydantic import BaseModel

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_TRANSACTIONAL_PATTERN = re.compile(
    r"\b(acheter|prix|tarif|devis|commander|abonnement|pas cher|promo|réduction)\b", re.IGNORECASE
)
_NAV_PATTERN = re.compile(r"\b(connexion|login|site officiel|avis clients?|contact|horaires)\b", re.IGNORECASE)
_STOPWORDS = {"le", "la", "les", "de", "des", "du", "un", "une", "et", "pour", "avec", "en", "sur", "à", "au"}


class KeywordData(BaseModel):
    term: str
    related_terms: list[str] = []
    source: Literal["serper", "searxng"]


async def search_keywords_serper(query: str) -> list[KeywordData]:
    """Recherches associées + "people also ask" via Serper (Google Search API)."""
    if not settings.SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY non configurée  utiliser search_keywords_searxng en repli.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query},
        )
        response.raise_for_status()
        body = response.json()

    related = [item["query"] for item in body.get("relatedSearches", []) if "query" in item]
    people_also_ask = [item["question"] for item in body.get("peopleAlsoAsk", []) if "question" in item]
    logger.info("keyword_research.serper_query", query=query, related_count=len(related) + len(people_also_ask))
    return [KeywordData(term=query, related_terms=related + people_also_ask, source="serper")]


async def search_keywords_searxng(query: str) -> list[KeywordData]:
    """Repli self-hosted : SearXNG n'a pas de notion native de "recherches
    associées"  variantes dérivées des titres de résultats retournés
    (heuristique, moins riche que Serper mais gratuite et souveraine)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{settings.SEARXNG_BASE_URL}/search", params={"q": query, "format": "json"})
        response.raise_for_status()
        body = response.json()

    titles = [r["title"] for r in body.get("results", [])[:10] if r.get("title")]
    logger.info("keyword_research.searxng_query", query=query, result_count=len(titles))
    return [KeywordData(term=query, related_terms=titles, source="searxng")]


async def search_keywords(query: str) -> list[KeywordData]:
    """Point d'entrée unique : Serper si configuré, SearXNG sinon  évite à
    chaque appelant de dupliquer la vérification de SERPER_API_KEY."""
    if settings.SERPER_API_KEY:
        return await search_keywords_serper(query)
    return await search_keywords_searxng(query)


def analyze_keyword_intent(keyword: str) -> Literal["info", "transactional", "nav"]:
    lowered = keyword.lower()
    if _TRANSACTIONAL_PATTERN.search(lowered):
        return "transactional"
    if _NAV_PATTERN.search(lowered):
        return "nav"
    return "info"


def cluster_keywords(keywords: list[str]) -> dict[str, list[str]]:
    """Clustering simple par mot-racine partagé : le mot le plus FRÉQUENT à
    travers l'ensemble des mots-clés (hors mots vides) sert de racine pour
    chaque terme qui le contient, la longueur ne servant qu'à départager les
    ex æquo. Priorise la fréquence sur la longueur pour que des
    reformulations proches d'un même thème (ex. "chaussures de running" et
    "meilleures chaussures running homme") rejoignent le même cluster plutôt
    que de se scinder sur un mot long mais isolé (vérifié : la variante
    "longueur seule" faisait exactement ça). Déterministe et sans dépendance
    externe ; pour un clustering sémantique plus fin, voir
    backend.core.memory.semantic_search / TextEmbedder."""
    tokenized = [[w for w in re.findall(r"\w+", kw.lower()) if w not in _STOPWORDS] for kw in keywords]

    word_counts: dict[str, int] = defaultdict(int)
    for words in tokenized:
        for word in set(words):  # une occurrence par mot-clé, pas par répétition dans la phrase
            word_counts[word] += 1

    clusters: dict[str, list[str]] = defaultdict(list)
    for kw, words in zip(keywords, tokenized):
        root = max(words, key=lambda w: (word_counts[w], len(w))) if words else kw.lower()
        clusters[root].append(kw)
    return dict(clusters)


def estimate_difficulty(keyword: str) -> float:
    """Heuristique 0-100 sans API tierce payante (Ahrefs/SEMrush non
    intégrées) : les requêtes longues (longue traîne) sont statistiquement
    moins compétitives ; les termes transactionnels sont plus disputés
    commercialement. À affiner avec des données réelles de positionnement
    une fois l'historique PostgreSQL(Keyword/KeywordHistory) suffisamment
    peuplé."""
    word_count = len(keyword.split())
    score = max(20.0, 80.0 - word_count * 10)
    if _TRANSACTIONAL_PATTERN.search(keyword.lower()):
        score = min(100.0, score + 15)
    return round(score, 1)
