"""LinkedIn profile enrichment via Proxycurl API."""

import json
import logging
from datetime import datetime

import httpx

from amida_agent.config import settings

logger = logging.getLogger(__name__)

PROXYCURL_BASE = "https://nubela.co/proxycurl/api/v2"


async def fetch_linkedin_profile(linkedin_url: str) -> dict | None:
    """Fetch a LinkedIn profile via Proxycurl. Returns raw API response dict."""
    if not settings.proxycurl_api_key:
        logger.error("PROXYCURL_API_KEY not set")
        return None

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{PROXYCURL_BASE}/linkedin",
            params={
                "linkedin_profile_url": linkedin_url,
                "use_cache": "if-recent",
                "skills": "include",
                "inferred_salary": "skip",
                "personal_email": "include",
                "personal_contact_number": "include",
            },
            headers={"Authorization": f"Bearer {settings.proxycurl_api_key}"},
        )

    if resp.status_code != 200:
        logger.error("Proxycurl error %d: %s", resp.status_code, resp.text[:200])
        return None

    return resp.json()


def parse_profile_data(raw: dict) -> dict:
    """Extract structured fields from a Proxycurl profile response."""
    experiences = raw.get("experiences") or []
    education = raw.get("education") or []

    current_title = ""
    current_company = ""
    if experiences:
        current_title = experiences[0].get("title", "")
        current_company = experiences[0].get("company", "")

    hired_date = None
    if experiences and experiences[0].get("starts_at"):
        starts = experiences[0]["starts_at"]
        try:
            hired_date = datetime(
                year=starts.get("year", 2024),
                month=starts.get("month", 1),
                day=starts.get("day", 1),
            )
        except (ValueError, TypeError):
            pass

    return {
        "first_name": raw.get("first_name", ""),
        "last_name": raw.get("last_name", ""),
        "full_name": raw.get("full_name", ""),
        "headline": raw.get("headline", ""),
        "summary": raw.get("summary", ""),
        "location": raw.get("city", ""),
        "country": raw.get("country_full_name", ""),
        "profile_photo_url": raw.get("profile_pic_url", ""),
        "title": current_title,
        "current_company": current_company,
        "skills": ", ".join(raw.get("skills", []) or []),
        "education_json": json.dumps(
            [
                {
                    "school": e.get("school", ""),
                    "degree": e.get("degree_name", ""),
                    "field": e.get("field_of_study", ""),
                    "start_year": (e.get("starts_at") or {}).get("year"),
                    "end_year": (e.get("ends_at") or {}).get("year"),
                }
                for e in education
            ]
        ),
        "experience_json": json.dumps(
            [
                {
                    "title": e.get("title", ""),
                    "company": e.get("company", ""),
                    "description": e.get("description", ""),
                    "start_year": (e.get("starts_at") or {}).get("year"),
                    "start_month": (e.get("starts_at") or {}).get("month"),
                    "end_year": (e.get("ends_at") or {}).get("year"),
                    "end_month": (e.get("ends_at") or {}).get("month"),
                    "is_current": e.get("ends_at") is None,
                }
                for e in experiences
            ]
        ),
        "hired_date": hired_date,
        "personal_emails": raw.get("personal_emails") or [],
        "phone_numbers": raw.get("personal_numbers") or [],
    }


def classify_role_type(title: str, skills: str) -> str:
    """Map a title + skills string to a RoleType value."""
    t = title.lower()
    s = skills.lower()

    if any(kw in t for kw in ["chief technology", "cto"]):
        return "cto"
    if any(kw in t for kw in ["chief data", "cdo"]):
        return "cdo"
    if any(kw in t for kw in ["head of analytics", "analytics lead", "analytics director"]):
        return "head_of_analytics"
    if any(kw in t for kw in [
        "ai ", "artificial intelligence", "machine learning", "ml ",
        "head of ai", "ai lead", "ai director", "vp ai",
    ]):
        return "ai_lead"
    if any(kw in t for kw in [
        "data science", "data lead", "data director", "head of data",
        "vp data", "data strategy",
    ]):
        return "data_lead"

    ai_skills = {"machine learning", "deep learning", "ai", "data science", "nlp", "tensorflow", "pytorch"}
    if any(sk in s for sk in ai_skills):
        return "ai_lead"

    return "other"
