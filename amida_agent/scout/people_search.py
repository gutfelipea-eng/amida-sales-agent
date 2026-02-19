"""Proxycurl Role Lookup scout — find AI/data leaders at PE firms."""

import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from sqlmodel import select

from amida_agent.config import settings
from amida_agent.database import get_session
from amida_agent.models import PEFirm, Prospect, SearchQuery

logger = logging.getLogger(__name__)

PROXYCURL_BASE = "https://nubela.co/proxycurl/api"
_DEDUP_DAYS = 7
_RATE_LIMIT_DELAY = 6  # seconds between Proxycurl requests

# Roles to search for at each firm
TARGET_ROLES = [
    "Head of AI",
    "Head of Data",
    "Chief Data Officer",
    "Chief Technology Officer",
    "VP of Data",
    "Director of Data Science",
    "Head of Machine Learning",
    "Head of Analytics",
]


async def search_firm_people(firm: PEFirm) -> list[dict]:
    """Search for AI/data leaders at a PE firm via Proxycurl Role Lookup.

    Uses /api/find/company/role/ endpoint.
    Returns list of dicts: {linkedin_url, title, firm_name, firm_id}.
    """
    if not settings.proxycurl_api_key:
        logger.error("PROXYCURL_API_KEY not set")
        return []

    if not firm.linkedin_url:
        logger.debug("No LinkedIn URL for %s, skipping people search", firm.name)
        return []

    results = []
    headers = {"Authorization": f"Bearer {settings.proxycurl_api_key}"}

    for role in TARGET_ROLES:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{PROXYCURL_BASE}/find/company/role/",
                params={
                    "company_name": firm.linkedin_url,
                    "role": role,
                    "enrich_profile": "skip",  # don't spend credits on full profile yet
                },
                headers=headers,
            )

        if resp.status_code == 200:
            data = resp.json()
            linkedin_url = data.get("linkedin_profile_url")
            if linkedin_url:
                results.append({
                    "linkedin_url": linkedin_url,
                    "title": role,
                    "firm_name": firm.name,
                    "firm_id": firm.id,
                })
                logger.info("Found %s at %s: %s", role, firm.name, linkedin_url)
        elif resp.status_code == 404:
            logger.debug("No %s found at %s", role, firm.name)
        elif resp.status_code == 429:
            logger.warning("Proxycurl 429 — pausing role lookups for %s", firm.name)
            await asyncio.sleep(30)
        else:
            logger.warning("Proxycurl role lookup error %d for %s/%s", resp.status_code, firm.name, role)

        # Rate limit: 6s between requests
        await asyncio.sleep(_RATE_LIMIT_DELAY)

    return results


async def search_all_firms() -> list[dict]:
    """Search all active PE firms for AI/data leaders. Dedup by 7-day window.

    Creates Prospect(status=new) for any new LinkedIn URLs found.
    Returns list of discovered people dicts.
    """
    results = []

    with get_session() as session:
        firms = session.exec(
            select(PEFirm).where(PEFirm.monitoring_active == True)  # noqa: E712
        ).all()

    cutoff = datetime.utcnow() - timedelta(days=_DEDUP_DAYS)

    for firm in firms:
        with get_session() as session:
            recent = session.exec(
                select(SearchQuery).where(
                    SearchQuery.query_type == "linkedin_people",
                    SearchQuery.pe_firm_id == firm.id,
                    SearchQuery.last_run_at >= cutoff,
                )
            ).first()

        if recent:
            logger.debug("Skipping people search for %s (last run %s)", firm.name, recent.last_run_at)
            continue

        people = await search_firm_people(firm)

        # Create Prospect stubs for new finds
        for person in people:
            with get_session() as session:
                existing = session.exec(
                    select(Prospect).where(Prospect.linkedin_url == person["linkedin_url"])
                ).first()

            if not existing:
                with get_session() as session:
                    prospect = Prospect(
                        full_name="",  # will be filled after enrichment
                        linkedin_url=person["linkedin_url"],
                        title=person["title"],
                        pe_firm_id=person["firm_id"],
                        source="people_search",
                    )
                    session.add(prospect)
                    session.commit()
                    logger.info("Created new prospect stub for %s at %s", person["title"], person["firm_name"])
            else:
                logger.debug("Prospect already exists: %s", person["linkedin_url"])

        results.extend(people)

        with get_session() as session:
            session.add(SearchQuery(
                query_type="linkedin_people",
                query_text=firm.name,
                pe_firm_id=firm.id,
                results_count=len(people),
                last_run_at=datetime.utcnow(),
            ))
            session.commit()

    logger.info("People search complete: %d results across %d firms", len(results), len(firms))
    return results
