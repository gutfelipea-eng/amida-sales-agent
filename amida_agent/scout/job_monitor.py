"""LinkedIn job monitor — Apify scraper for AI/data hiring signals at PE firms."""

import logging
from datetime import datetime, timedelta

from sqlmodel import select

from amida_agent.database import get_session
from amida_agent.models import PEFirm, SearchQuery
from amida_agent.scout.apify_client import run_actor

logger = logging.getLogger(__name__)

_ACTOR_ID = "anchor/linkedin-jobs-scraper"
_DEDUP_HOURS = 24

# Job titles / keywords that indicate AI/data hiring
AI_JOB_KEYWORDS = [
    "artificial intelligence", "machine learning", "data science",
    "data engineer", "ml engineer", "ai engineer",
    "head of data", "head of ai", "chief data",
    "nlp", "deep learning", "computer vision",
    "data platform", "data strategy", "analytics",
]


async def scan_firm_jobs(firm: PEFirm) -> list[dict]:
    """Scan LinkedIn jobs for a single PE firm via Apify.

    Returns list of job dicts that match AI/data keywords:
    {title, company, location, url, posted_at}.
    Jobs are *signals*, not prospects directly.
    """
    if not firm.name:
        return []

    run_input = {
        "searchUrl": f"https://www.linkedin.com/jobs/search/?keywords={firm.name}&f_TPR=r604800",
        "maxItems": 50,
        "proxy": {"useApifyProxy": True},
    }

    logger.info("Scanning jobs for %s", firm.name)
    raw_jobs = await run_actor(_ACTOR_ID, run_input)

    # Filter to AI/data-relevant jobs
    relevant = []
    for job in raw_jobs:
        title = job.get("title", "")
        if _matches_ai_keywords(title):
            relevant.append({
                "title": title,
                "company": job.get("companyName", firm.name),
                "location": job.get("location", ""),
                "url": job.get("url", ""),
                "posted_at": job.get("postedAt", ""),
                "firm_name": firm.name,
                "firm_id": firm.id,
            })

    logger.info("Found %d/%d AI-relevant jobs for %s", len(relevant), len(raw_jobs), firm.name)
    return relevant


def _matches_ai_keywords(title: str) -> bool:
    """Check if a job title matches any AI/data keyword."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in AI_JOB_KEYWORDS)


async def scan_all_firms() -> list[dict]:
    """Scan jobs for all active PE firms. Dedup by 24h SearchQuery window.

    Returns flat list of relevant job dicts.
    """
    results = []

    with get_session() as session:
        firms = session.exec(
            select(PEFirm).where(PEFirm.monitoring_active == True)  # noqa: E712
        ).all()

    cutoff = datetime.utcnow() - timedelta(hours=_DEDUP_HOURS)

    for firm in firms:
        with get_session() as session:
            recent = session.exec(
                select(SearchQuery).where(
                    SearchQuery.query_type == "linkedin_jobs",
                    SearchQuery.pe_firm_id == firm.id,
                    SearchQuery.last_run_at >= cutoff,
                )
            ).first()

        if recent:
            logger.debug("Skipping job scan for %s (last run %s)", firm.name, recent.last_run_at)
            continue

        jobs = await scan_firm_jobs(firm)
        results.extend(jobs)

        with get_session() as session:
            session.add(SearchQuery(
                query_type="linkedin_jobs",
                query_text=firm.name,
                pe_firm_id=firm.id,
                results_count=len(jobs),
                last_run_at=datetime.utcnow(),
            ))
            session.commit()

    logger.info("Job scan complete: %d relevant jobs across %d firms", len(results), len(firms))
    return results
