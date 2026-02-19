"""Company research — enrich PE firm context for outreach personalization."""

import json
import logging

import httpx

from amida_agent.config import settings

logger = logging.getLogger(__name__)

PROXYCURL_BASE = "https://nubela.co/proxycurl/api"


async def fetch_company_profile(linkedin_url: str) -> dict | None:
    """Fetch company data via Proxycurl Company Profile API."""
    if not settings.proxycurl_api_key:
        logger.error("PROXYCURL_API_KEY not set")
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{PROXYCURL_BASE}/linkedin/company",
                params={
                    "url": linkedin_url,
                    "use_cache": "if-recent",
                },
                headers={"Authorization": f"Bearer {settings.proxycurl_api_key}"},
            )

        if resp.status_code != 200:
            logger.error("Proxycurl company error %d: %s", resp.status_code, resp.text[:200])
            return None

        return resp.json()
    except Exception:
        logger.exception("Failed to fetch company profile: %s", linkedin_url)
        return None


def parse_company_data(raw: dict) -> dict:
    """Extract key company fields from Proxycurl response."""
    return {
        "name": raw.get("name", ""),
        "description": raw.get("description", ""),
        "industry": raw.get("industry", ""),
        "specialities": raw.get("specialities") or [],
        "website": raw.get("website", ""),
        "company_size": raw.get("company_size_on_linkedin"),
        "headquarters": raw.get("hq", {}).get("city", "") if raw.get("hq") else "",
        "founded_year": raw.get("founded_year"),
        "tagline": raw.get("tagline", ""),
        "follower_count": raw.get("follower_count", 0),
        "updates": [
            {
                "text": u.get("text", "")[:500],
                "date": u.get("posted_on", {}).get("day") if u.get("posted_on") else None,
            }
            for u in (raw.get("updates") or [])[:5]
        ],
    }


def build_company_context(firm_data: dict, company_profile: dict | None) -> str:
    """Build a JSON string of company context for AI prompts."""
    context = {
        "firm_name": firm_data.get("name", ""),
        "website": firm_data.get("website", ""),
        "country": firm_data.get("country", ""),
        "hq_city": firm_data.get("hq_city", ""),
        "aum_billion_eur": firm_data.get("aum_billion_eur"),
        "sectors": firm_data.get("sectors", ""),
    }
    if company_profile:
        context.update({
            "description": company_profile.get("description", ""),
            "industry": company_profile.get("industry", ""),
            "specialities": company_profile.get("specialities", []),
            "company_size": company_profile.get("company_size"),
            "tagline": company_profile.get("tagline", ""),
            "recent_updates": company_profile.get("updates", []),
        })
    return json.dumps(context)
