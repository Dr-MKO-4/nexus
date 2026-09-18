"""Outil d'audit technique SEO : PageSpeed Insights, balises meta, données
structurées, maillage interne, compatibilité mobile.

Point de vigilance documenté (vérifié, pas supposé) : l'API dédiée Google
Mobile-Friendly Test a été DÉPRÉCIÉE en décembre 2023  `check_mobile_friendly`
utilise donc une heuristique locale (présence du meta viewport), pas un
appel à une API désormais inexistante.
"""

import httpx
import structlog
from bs4 import BeautifulSoup
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

_PAGESPEED_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class SpeedData(BaseModel):
    url: str
    performance_score: float  # 0-100
    largest_contentful_paint_ms: float | None = None
    cumulative_layout_shift: float | None = None


class MetaTagAudit(BaseModel):
    url: str
    title: str | None
    title_length: int
    meta_description: str | None
    meta_description_length: int
    has_canonical: bool
    has_viewport: bool


class StructuredDataAudit(BaseModel):
    url: str
    schema_types_found: list[str]
    has_structured_data: bool


class InternalLinksAudit(BaseModel):
    sitemap_url: str
    total_urls: int
    broken_links: list[str]


async def audit_page_speed(url: str) -> SpeedData:
    """PageSpeed Insights fonctionne sans clé API (débit limité mais
    fonctionnel)  aucune credential dédiée dans settings.py à ce jour."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(_PAGESPEED_API, params={"url": url, "category": "PERFORMANCE"})
        response.raise_for_status()
        body = response.json()

    lighthouse = body.get("lighthouseResult", {})
    performance_category = lighthouse.get("categories", {}).get("performance", {})
    audits = lighthouse.get("audits", {})
    score = performance_category.get("score")

    logger.info("technical_audit.page_speed", url=url, score=score)
    return SpeedData(
        url=url,
        performance_score=round((score or 0) * 100, 1),
        largest_contentful_paint_ms=audits.get("largest-contentful-paint", {}).get("numericValue"),
        cumulative_layout_shift=audits.get("cumulative-layout-shift", {}).get("numericValue"),
    )


async def _fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "NexusBot/1.0 (SEO audit)"})
        response.raise_for_status()
        return response.text


async def check_meta_tags(url: str) -> MetaTagAudit:
    html = await _fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("title")
    title = title_tag.text.strip() if title_tag else None

    description_tag = soup.find("meta", attrs={"name": "description"})
    description = description_tag.get("content", "").strip() if description_tag else None

    has_canonical = soup.find("link", attrs={"rel": "canonical"}) is not None
    has_viewport = soup.find("meta", attrs={"name": "viewport"}) is not None

    return MetaTagAudit(
        url=url,
        title=title,
        title_length=len(title) if title else 0,
        meta_description=description,
        meta_description_length=len(description) if description else 0,
        has_canonical=has_canonical,
        has_viewport=has_viewport,
    )


async def check_structured_data(url: str) -> StructuredDataAudit:
    """Détecte les blocs JSON-LD (`<script type="application/ld+json">`),
    format de données structurées le plus courant en SEO moderne (Schema.org)
     les formats Microdata/RDFa plus anciens ne sont pas couverts."""
    html = await _fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    schema_types: list[str] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        import json

        try:
            data = json.loads(script.string or "{}")
        except json.JSONDecodeError:
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if isinstance(entry, dict) and "@type" in entry:
                schema_types.append(entry["@type"])

    return StructuredDataAudit(url=url, schema_types_found=schema_types, has_structured_data=bool(schema_types))


async def audit_internal_links(sitemap_url: str) -> InternalLinksAudit:
    """Parse un sitemap.xml et vérifie que chaque URL listée répond (HEAD,
    pas GET  plus léger pour un sitemap pouvant contenir des milliers
    d'entrées) sans erreur 4xx/5xx."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(sitemap_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "xml")
        urls = [loc.text.strip() for loc in soup.find_all("loc")]

        broken_links: list[str] = []
        for url in urls:
            try:
                head_response = await client.head(url, follow_redirects=True, timeout=10.0)
                if head_response.status_code >= 400:
                    broken_links.append(url)
            except httpx.HTTPError:
                broken_links.append(url)

    logger.info("technical_audit.internal_links", sitemap_url=sitemap_url, total=len(urls), broken=len(broken_links))
    return InternalLinksAudit(sitemap_url=sitemap_url, total_urls=len(urls), broken_links=broken_links)


async def check_mobile_friendly(url: str) -> bool:
    """Heuristique locale (pas d'API Google dédiée disponible  voir
    docstring de module) : le signal principal et fiable est la présence
    d'un meta viewport ; la détection de media queries n'est qu'indicative
    (elle ne couvre que le CSS inline `<style>`, pas les feuilles externes
    liées) et ne doit donc pas, à elle seule, faire échouer le diagnostic."""
    html = await _fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    has_viewport = soup.find("meta", attrs={"name": "viewport"}) is not None
    return has_viewport
