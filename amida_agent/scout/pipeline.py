"""Scout pipeline — orchestrate discovery → pre-score → enrich → dossier → save."""

import asyncio
import json
import logging
from datetime import datetime

from sqlmodel import select

from amida_agent.config import settings
from amida_agent.database import get_session
from amida_agent.models import (
    ActivityLog,
    Channel,
    OutreachDraft,
    PEFirm,
    Prospect,
    ProspectStatus,
    RoleType,
)
from amida_agent.notifications.notifier import notify_new_lead
from amida_agent.research.company_research import (
    build_company_context,
    fetch_company_profile,
    parse_company_data,
)
from amida_agent.research.dossier_builder import build_dossier, score_relevance
from amida_agent.research.email_finder import domain_from_website, find_email
from amida_agent.research.enricher import (
    classify_role_type,
    fetch_linkedin_profile,
    parse_profile_data,
)
from amida_agent.scout.scorer import pre_score, should_enrich, should_notify

logger = logging.getLogger(__name__)


async def process_discovered_lead(
    linkedin_url: str,
    title: str = "",
    firm_name: str = "",
    source: str = "",
    firm_id: int | None = None,
    has_hiring_signal: bool = False,
    has_news_mention: bool = False,
) -> int | None:
    """Process a single discovered lead through the full pipeline.

    Steps: dedup → pre-score → enrich → email → dossier → full-score → save → notify.
    Returns prospect ID or None if skipped/failed.
    """
    # --- Dedup ---
    with get_session() as session:
        existing = session.exec(
            select(Prospect).where(Prospect.linkedin_url == linkedin_url)
        ).first()
    if existing:
        logger.debug("Skipping duplicate: %s (prospect ID %d)", linkedin_url, existing.id)
        return existing.id

    # --- Pre-score ---
    score, breakdown = pre_score(
        title=title,
        company=firm_name,
        source=source,
        has_hiring_signal=has_hiring_signal,
        has_news_mention=has_news_mention,
    )
    logger.info("Pre-score for %s at %s: %.2f %s", title, firm_name, score, breakdown)

    if not should_enrich(score):
        logger.info("Below enrichment threshold (%.2f < %.2f), skipping: %s",
                     score, settings.enrichment_threshold, linkedin_url)
        return None

    # --- Enrich via Proxycurl ---
    raw_profile = await fetch_linkedin_profile(linkedin_url)
    if not raw_profile:
        logger.warning("Could not enrich %s", linkedin_url)
        return None

    profile = parse_profile_data(raw_profile)
    logger.info("Enriched: %s — %s at %s", profile["full_name"], profile["title"], profile["current_company"])

    # --- Match to PE firm ---
    firm_data = {}
    if not firm_id:
        with get_session() as session:
            firms = session.exec(select(PEFirm)).all()
            for firm in firms:
                if firm.name.lower() in profile["current_company"].lower():
                    firm_id = firm.id
                    firm_data = _firm_to_dict(firm)
                    break
    else:
        with get_session() as session:
            firm = session.get(PEFirm, firm_id)
            if firm:
                firm_data = _firm_to_dict(firm)

    # --- Find email ---
    email_info = None
    email = None
    if profile.get("personal_emails"):
        email = profile["personal_emails"][0]
    elif firm_data.get("website"):
        domain = domain_from_website(firm_data["website"])
        email_info = await find_email(profile["first_name"], profile["last_name"], domain)
        if email_info:
            email = email_info["email"]

    # --- Build company context & dossier ---
    company_profile = None
    if firm_data.get("linkedin_url"):
        raw_company = await fetch_company_profile(firm_data["linkedin_url"])
        if raw_company:
            company_profile = parse_company_data(raw_company)

    company_context = build_company_context(firm_data, company_profile) if firm_data else None
    role_type = classify_role_type(profile.get("title", ""), profile.get("skills", ""))
    relevance, full_breakdown = score_relevance(profile, company_context)
    dossier = build_dossier(profile, company_context, email_info)

    # --- Save prospect ---
    with get_session() as session:
        prospect = Prospect(
            linkedin_url=linkedin_url,
            first_name=profile["first_name"],
            last_name=profile["last_name"],
            full_name=profile["full_name"],
            title=profile.get("title", ""),
            headline=profile.get("headline", ""),
            summary=profile.get("summary", ""),
            location=profile.get("location", ""),
            skills=profile.get("skills", ""),
            education=profile.get("education_json", "[]"),
            experience=profile.get("experience_json", "[]"),
            profile_photo_url=profile.get("profile_photo_url", ""),
            role_type=RoleType(role_type),
            relevance_score=relevance,
            score_breakdown=json.dumps(full_breakdown),
            dossier=dossier,
            company_context=company_context or "",
            pe_firm_id=firm_id,
            hired_date=profile.get("hired_date"),
            email=email,
            source=source,
            status=ProspectStatus.ready,
        )
        session.add(prospect)
        session.add(ActivityLog(
            action="auto_discovered",
            details=json.dumps({
                "source": source,
                "pre_score": score,
                "pre_breakdown": breakdown,
                "full_score": relevance,
            }),
        ))
        session.commit()
        session.refresh(prospect)
        prospect_id = prospect.id

        # Link activity log to prospect
        activity = session.exec(
            select(ActivityLog).where(
                ActivityLog.prospect_id == None,  # noqa: E711
                ActivityLog.action == "auto_discovered",
            ).order_by(ActivityLog.id.desc())  # type: ignore[union-attr]
        ).first()
        if activity:
            activity.prospect_id = prospect_id
            session.commit()

    logger.info("Saved prospect %d: %s (score %.2f)", prospect_id, profile["full_name"], relevance)

    # --- Compose AI draft if Anthropic key available ---
    if settings.anthropic_api_key:
        try:
            from amida_agent.ai.composer import compose_email
            subject, body = compose_email(dossier, sequence_step=1)
            with get_session() as session:
                session.add(OutreachDraft(
                    prospect_id=prospect_id,
                    channel=Channel.email,
                    sequence_step=1,
                    subject=subject,
                    body=body,
                ))
                prospect = session.get(Prospect, prospect_id)
                if prospect:
                    prospect.status = ProspectStatus.drafted
                    prospect.updated_at = datetime.utcnow()
                session.add(ActivityLog(
                    prospect_id=prospect_id,
                    action="email_drafted",
                    channel=Channel.email,
                    details=f"Auto-drafted step 1: {subject}",
                ))
                session.commit()
        except Exception as e:
            logger.warning("Auto-draft failed for prospect %d: %s", prospect_id, e)

    # --- Notify if high score ---
    if should_notify(relevance):
        notify_new_lead(profile["full_name"], firm_name or profile["current_company"], relevance)

    return prospect_id


async def run_full_scan() -> dict:
    """Run all 3 scouts and process results through the pipeline.

    Returns summary dict: {news_articles, jobs_found, people_found, prospects_created}.
    """
    from amida_agent.scout.job_monitor import scan_all_firms as scan_jobs
    from amida_agent.scout.news_monitor import scan_all_firms as scan_news
    from amida_agent.scout.people_search import search_all_firms as search_people

    summary = {
        "news_articles": 0,
        "jobs_found": 0,
        "people_found": 0,
        "prospects_created": 0,
    }

    # --- News scan (free) ---
    logger.info("=== Starting news scan ===")
    try:
        news = await scan_news()
        summary["news_articles"] = len(news)

        # Build a set of firm IDs with hiring signals from news
        firms_with_news: dict[int, bool] = {}
        for article in news:
            fid = article.get("firm_id")
            if fid:
                if article.get("has_hiring_signal"):
                    firms_with_news[fid] = True
                elif fid not in firms_with_news:
                    firms_with_news[fid] = False
    except Exception as e:
        logger.error("News scan failed: %s", e)
        news = []
        firms_with_news = {}

    # --- Job scan (Apify) ---
    logger.info("=== Starting job scan ===")
    try:
        jobs = await scan_jobs()
        summary["jobs_found"] = len(jobs)

        firms_with_jobs: set[int] = set()
        for job in jobs:
            fid = job.get("firm_id")
            if fid:
                firms_with_jobs.add(fid)
    except Exception as e:
        logger.error("Job scan failed: %s", e)
        jobs = []
        firms_with_jobs = set()

    # --- People search (Proxycurl) ---
    logger.info("=== Starting people search ===")
    try:
        people = await search_people()
        summary["people_found"] = len(people)
    except Exception as e:
        logger.error("People search failed: %s", e)
        people = []

    # --- Process discovered people through pipeline ---
    logger.info("=== Processing %d discovered leads ===", len(people))
    for person in people:
        fid = person.get("firm_id")
        try:
            prospect_id = await process_discovered_lead(
                linkedin_url=person["linkedin_url"],
                title=person.get("title", ""),
                firm_name=person.get("firm_name", ""),
                source="people_search",
                firm_id=fid,
                has_hiring_signal=fid in firms_with_jobs if fid else False,
                has_news_mention=fid in firms_with_news if fid else False,
            )
            if prospect_id:
                summary["prospects_created"] += 1
        except Exception as e:
            logger.error("Pipeline error for %s: %s", person.get("linkedin_url", "?"), e)

    logger.info("Full scan complete: %s", summary)
    return summary


def _firm_to_dict(firm: PEFirm) -> dict:
    """Convert PEFirm model to dict for pipeline use."""
    return {
        "name": firm.name,
        "website": firm.website,
        "linkedin_url": firm.linkedin_url,
        "country": firm.country,
        "hq_city": firm.hq_city,
        "aum_billion_eur": firm.aum_billion_eur,
        "sectors": firm.sectors,
    }
