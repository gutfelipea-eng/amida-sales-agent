"""End-to-end: LinkedIn URL → enrich → dossier → AI email draft → save to DB.

Usage:
    python scripts/research_prospect.py --linkedin "https://www.linkedin.com/in/someone/"
    python scripts/research_prospect.py --prospect-id 1   # re-research existing prospect
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import select

from amida_agent.config import settings
from amida_agent.database import get_session, init_db
from amida_agent.models import (
    ActivityLog,
    Channel,
    OutreachDraft,
    PEFirm,
    Prospect,
    ProspectStatus,
    RoleType,
)
from amida_agent.research.enricher import (
    classify_role_type,
    fetch_linkedin_profile,
    parse_profile_data,
)
from amida_agent.research.email_finder import domain_from_website, find_email
from amida_agent.research.company_research import (
    build_company_context,
    fetch_company_profile,
    parse_company_data,
)
from amida_agent.research.dossier_builder import build_dossier, score_relevance
from amida_agent.ai.composer import compose_email


async def research_from_linkedin(linkedin_url: str) -> int | None:
    """Full pipeline: LinkedIn URL → prospect in DB with draft. Returns prospect ID."""
    init_db()

    print(f"\n[1/6] Fetching LinkedIn profile: {linkedin_url}")
    raw_profile = await fetch_linkedin_profile(linkedin_url)
    if not raw_profile:
        print("  ERROR: Could not fetch profile. Check PROXYCURL_API_KEY.")
        return None

    profile = parse_profile_data(raw_profile)
    print(f"  Found: {profile['full_name']} — {profile['title']} at {profile['current_company']}")

    # Match to PE firm
    print("\n[2/6] Matching to PE firm...")
    firm_id = None
    firm_data = {}
    with get_session() as session:
        firms = session.exec(select(PEFirm)).all()
        for firm in firms:
            if firm.name.lower() in profile["current_company"].lower():
                firm_id = firm.id
                firm_data = {
                    "name": firm.name,
                    "website": firm.website,
                    "linkedin_url": firm.linkedin_url,
                    "country": firm.country,
                    "hq_city": firm.hq_city,
                    "aum_billion_eur": firm.aum_billion_eur,
                    "sectors": firm.sectors,
                }
                print(f"  Matched: {firm.name}")
                break
    if not firm_id:
        print("  No PE firm match found (prospect may still be relevant)")

    # Find email
    print("\n[3/6] Finding email...")
    email_info = None
    email = None
    if profile.get("personal_emails"):
        email = profile["personal_emails"][0]
        print(f"  Found personal email from profile: {email}")
    elif firm_data.get("website"):
        domain = domain_from_website(firm_data["website"])
        email_info = await find_email(profile["first_name"], profile["last_name"], domain)
        if email_info:
            email = email_info["email"]
            print(f"  Found via Hunter.io: {email} (score: {email_info['score']})")
        else:
            print("  No email found via Hunter.io")
    else:
        print("  Skipped (no company domain)")

    # Build company context & dossier
    print("\n[4/6] Building dossier...")
    company_profile = None
    if firm_data.get("linkedin_url"):
        print(f"  Fetching company LinkedIn: {firm_data['linkedin_url']}")
        raw_company = await fetch_company_profile(firm_data["linkedin_url"])
        if raw_company:
            company_profile = parse_company_data(raw_company)
    company_context = build_company_context(firm_data, company_profile) if firm_data else None
    role_type = classify_role_type(profile.get("title", ""), profile.get("skills", ""))
    relevance, breakdown = score_relevance(profile, company_context)
    dossier = build_dossier(profile, company_context, email_info)
    print(f"  Relevance score: {relevance:.0%}")
    print(f"  Breakdown: {json.dumps(breakdown, indent=2)}")

    # Save prospect
    print("\n[5/6] Saving to database...")
    with get_session() as session:
        # Check for existing prospect with same LinkedIn
        existing = session.exec(
            select(Prospect).where(Prospect.linkedin_url == linkedin_url)
        ).first()

        if existing:
            prospect = existing
            print(f"  Updating existing prospect ID {prospect.id}")
        else:
            prospect = Prospect(linkedin_url=linkedin_url, source="manual_research")
            session.add(prospect)

        prospect.first_name = profile["first_name"]
        prospect.last_name = profile["last_name"]
        prospect.full_name = profile["full_name"]
        prospect.title = profile.get("title", "")
        prospect.headline = profile.get("headline", "")
        prospect.summary = profile.get("summary", "")
        prospect.location = profile.get("location", "")
        prospect.skills = profile.get("skills", "")
        prospect.education = profile.get("education_json", "[]")
        prospect.experience = profile.get("experience_json", "[]")
        prospect.profile_photo_url = profile.get("profile_photo_url", "")
        prospect.role_type = RoleType(role_type)
        prospect.relevance_score = relevance
        prospect.score_breakdown = json.dumps(breakdown)
        prospect.dossier = dossier
        prospect.company_context = company_context or ""
        prospect.pe_firm_id = firm_id
        prospect.hired_date = profile.get("hired_date")
        prospect.status = ProspectStatus.ready
        prospect.updated_at = datetime.utcnow()

        if email:
            prospect.email = email

        session.add(ActivityLog(
            prospect_id=prospect.id,
            action="researched",
            details=f"Enriched from LinkedIn, score={relevance:.2f}",
        ))

        session.commit()
        session.refresh(prospect)
        prospect_id = prospect.id
        print(f"  Saved prospect ID: {prospect_id}")

    # Compose AI email draft
    print("\n[6/6] Composing AI email draft...")
    if not settings.anthropic_api_key:
        print("  SKIPPED: ANTHROPIC_API_KEY not set. Set it in .env to generate drafts.")
        return prospect_id

    subject, body = compose_email(dossier, sequence_step=1)
    print(f"  Subject: {subject}")
    print(f"  Body:\n{body}\n")

    with get_session() as session:
        draft = OutreachDraft(
            prospect_id=prospect_id,
            channel=Channel.email,
            sequence_step=1,
            subject=subject,
            body=body,
        )
        session.add(draft)

        prospect = session.get(Prospect, prospect_id)
        if prospect:
            prospect.status = ProspectStatus.drafted
            prospect.updated_at = datetime.utcnow()

        session.add(ActivityLog(
            prospect_id=prospect_id,
            action="email_drafted",
            channel=Channel.email,
            details=f"Step 1 draft: {subject}",
        ))
        session.commit()
        print(f"  Draft saved! Go to http://127.0.0.1:8000/approve to review.")

    return prospect_id


async def research_existing(prospect_id: int) -> int | None:
    """Re-research an existing prospect by ID."""
    init_db()
    with get_session() as session:
        prospect = session.get(Prospect, prospect_id)
        if not prospect:
            print(f"Prospect ID {prospect_id} not found.")
            return None
        if not prospect.linkedin_url:
            print(f"Prospect {prospect.full_name} has no LinkedIn URL.")
            return None
        linkedin_url = prospect.linkedin_url

    return await research_from_linkedin(linkedin_url)


def main():
    parser = argparse.ArgumentParser(description="Research a prospect end-to-end")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--linkedin", help="LinkedIn profile URL")
    group.add_argument("--prospect-id", type=int, help="Existing prospect ID to re-research")
    args = parser.parse_args()

    if args.linkedin:
        result = asyncio.run(research_from_linkedin(args.linkedin))
    else:
        result = asyncio.run(research_existing(args.prospect_id))

    if result:
        print(f"\nDone! Prospect ID: {result}")
        print(f"View: http://127.0.0.1:8000/prospects/{result}")
    else:
        print("\nFailed. Check logs above.")


if __name__ == "__main__":
    main()
