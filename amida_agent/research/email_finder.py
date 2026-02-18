"""Email finding via Hunter.io API."""

import logging

import httpx

from amida_agent.config import settings

logger = logging.getLogger(__name__)

HUNTER_BASE = "https://api.hunter.io/v2"


async def find_email(
    first_name: str,
    last_name: str,
    domain: str,
) -> dict | None:
    """Find a professional email via Hunter.io email-finder endpoint.

    Returns dict with 'email', 'score', 'position', 'sources' or None.
    """
    if not settings.hunter_api_key:
        logger.error("HUNTER_API_KEY not set")
        return None

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{HUNTER_BASE}/email-finder",
            params={
                "domain": domain,
                "first_name": first_name,
                "last_name": last_name,
                "api_key": settings.hunter_api_key,
            },
        )

    if resp.status_code != 200:
        logger.error("Hunter.io error %d: %s", resp.status_code, resp.text[:200])
        return None

    data = resp.json().get("data", {})
    if not data.get("email"):
        logger.info("No email found for %s %s @ %s", first_name, last_name, domain)
        return None

    return {
        "email": data["email"],
        "score": data.get("score", 0),
        "position": data.get("position", ""),
        "sources": data.get("sources", []),
    }


async def verify_email(email: str) -> dict | None:
    """Verify an email address via Hunter.io."""
    if not settings.hunter_api_key:
        logger.error("HUNTER_API_KEY not set")
        return None

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{HUNTER_BASE}/email-verifier",
            params={
                "email": email,
                "api_key": settings.hunter_api_key,
            },
        )

    if resp.status_code != 200:
        logger.error("Hunter.io verify error %d: %s", resp.status_code, resp.text[:200])
        return None

    data = resp.json().get("data", {})
    return {
        "email": data.get("email", email),
        "result": data.get("result", "unknown"),  # deliverable, undeliverable, risky, unknown
        "score": data.get("score", 0),
        "smtp_check": data.get("smtp_check", False),
    }


def domain_from_website(website: str) -> str:
    """Extract domain from a website URL."""
    domain = website.lower().strip()
    for prefix in ["https://", "http://", "www."]:
        domain = domain.removeprefix(prefix)
    return domain.split("/")[0]
