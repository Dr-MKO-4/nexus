"""Outils SEO : analyse de mots-clés, crawl technique, suivi de positions (intégrations tierces)."""

from backend.tools.seo.google_search_console import GoogleSearchConsoleClient
from backend.tools.seo.keyword_research import (
    analyze_keyword_intent,
    cluster_keywords,
    estimate_difficulty,
    search_keywords,
    search_keywords_searxng,
    search_keywords_serper,
)
from backend.tools.seo.technical_audit import (
    audit_internal_links,
    audit_page_speed,
    check_meta_tags,
    check_mobile_friendly,
    check_structured_data,
)

__all__ = [
    "GoogleSearchConsoleClient",
    "search_keywords",
    "search_keywords_serper",
    "search_keywords_searxng",
    "analyze_keyword_intent",
    "cluster_keywords",
    "estimate_difficulty",
    "audit_page_speed",
    "check_meta_tags",
    "check_structured_data",
    "audit_internal_links",
    "check_mobile_friendly",
]
