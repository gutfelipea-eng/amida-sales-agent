"""Google News RSS scout — find PE + AI announcements for free."""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import quote_plus

import httpx
from sqlmodel import select

from amida_agent.database import get_session
from amida_agent.models import PEFirm, SearchQuery

logger = logging.getLogger(__name__)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_USER_AGENT = "AmidaAgent/1.0 (news-monitor)"
_DEDUP_HOURS = 24

# Keywords that signal AI/data hiring or investment
_HIRING_KEYWORDS = [
    "hires", "hired", "appoints", "appointed", "names", "named",
    "joins", "joined", "recruits", "recruited",
    "head of ai", "head of data", "chief data", "chief ai",
    "data science", "machine learning", "artificial intelligence",
    "ai strategy", "digital transformation", "data platform",
]


async def search_firm_news(firm_name: str) -> list[dict]:
    """Search Google News RSS for a firm + AI-related mentions.

    Returns list of dicts: {title, link, published, has_hiring_signal}.
    """
    query = f'"{firm_name}" AND (AI OR "data science" OR "machine learning")'
    url = f"{_GOOGLE_NEWS_RSS}?q={quote_plus(query)}&hl=en&gl=US&ceid=US:en"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers={"User-Agent": _USER_AGENT})

    if resp.status_code != 200:
        logger.warning("Google News RSS error %d for %s", resp.status_code, firm_name)
        return []

    return _parse_rss(resp.text)


def _parse_rss(xml_text: str) -> list[dict]:
    """Parse Google News RSS XML into article dicts."""
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("RSS parse error: %s", e)
        return []

    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")

        title = unescape(title_el.text) if title_el is not None and title_el.text else ""
        link = link_el.text if link_el is not None and link_el.text else ""
        published = pub_el.text if pub_el is not None and pub_el.text else ""

        articles.append({
            "title": title,
            "link": link,
            "published": published,
            "has_hiring_signal": _has_hiring_signal(title),
        })

    return articles


def _has_hiring_signal(text: str) -> bool:
    """Check if a news title contains a hiring/appointment signal."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in _HIRING_KEYWORDS)


async def scan_all_firms() -> list[dict]:
    """Scan news for all active PE firms. Dedup by 24h SearchQuery window.

    Returns flat list of {firm_name, firm_id, title, link, published, has_hiring_signal}.
    """
    results = []

    with get_session() as session:
        firms = session.exec(
            select(PEFirm).where(PEFirm.monitoring_active == True)  # noqa: E712
        ).all()

    cutoff = datetime.utcnow() - timedelta(hours=_DEDUP_HOURS)

    for firm in firms:
        # Dedup: skip if we searched this firm recently
        with get_session() as session:
            recent = session.exec(
                select(SearchQuery).where(
                    SearchQuery.query_type == "google_news",
                    SearchQuery.pe_firm_id == firm.id,
                    SearchQuery.last_run_at >= cutoff,
                )
            ).first()

        if recent:
            logger.debug("Skipping news scan for %s (last run %s)", firm.name, recent.last_run_at)
            continue

        logger.info("Scanning news for %s", firm.name)
        articles = await search_firm_news(firm.name)

        for article in articles:
            article["firm_name"] = firm.name
            article["firm_id"] = firm.id
        results.extend(articles)

        # Record the search
        with get_session() as session:
            session.add(SearchQuery(
                query_type="google_news",
                query_text=firm.name,
                pe_firm_id=firm.id,
                results_count=len(articles),
                last_run_at=datetime.utcnow(),
            ))
            session.commit()

    logger.info("News scan complete: %d articles from %d firms", len(results), len(firms))
    return results
