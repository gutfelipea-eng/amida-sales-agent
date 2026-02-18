"""Seed realistic test prospects, drafts, and activity for demo purposes."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import select

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

now = datetime.now(timezone.utc).replace(tzinfo=None)


def get_firm_id(session, name):
    firm = session.exec(select(PEFirm).where(PEFirm.name == name)).first()
    return firm.id if firm else None


PROSPECTS = [
    # --- MEETING stage (furthest along) ---
    {
        "first_name": "Mikael",
        "last_name": "Ström",
        "title": "Director of AI",
        "role_type": RoleType.ai_lead,
        "firm": "Hg Capital",
        "email": "mikael.strom@example.com",
        "location": "London, UK",
        "headline": "AI-driven software investing",
        "source": "google_news",
        "relevance_score": 0.89,
        "status": ProspectStatus.meeting,
        "hired_date": now - timedelta(days=120),
        "summary": "PhD Machine Learning, Imperial College. 4 months into Director of AI at Hg Capital. Previously principal ML engineer at DeepMind. Meeting booked for next week.",
        "dossier": "# Mikael Ström — Hg Capital\n\n## Background\n- PhD Machine Learning, Imperial College London\n- Strong publication record in NLP\n\n## Career\n- **Director of AI, Hg Capital** (Oct 2025 – Present)\n- **Principal ML Engineer, DeepMind** (2019–2025)\n\n## Key Signals\n- 4 months in — past onboarding, now building AI strategy\n- Hg has €65B AUM with 40+ software companies\n- DeepMind background = deep technical credibility\n\n## Meeting Notes\n- Interested in Amida's portfolio-wide AI deployment model\n- Hg has 40+ software companies that could benefit\n- Follow up with case studies from similar PE deployments",
        "education": json.dumps([
            {"school": "Imperial College London", "degree": "PhD", "field": "Machine Learning", "start_date": "2015", "end_date": "2019"},
        ]),
        "experience": json.dumps([
            {"title": "Director of AI", "company": "Hg Capital", "start_date": "Oct 2025"},
            {"title": "Principal ML Engineer", "company": "DeepMind", "start_date": "2019", "end_date": "2025"},
        ]),
        "score_breakdown": json.dumps({
            "education_match": 0.95,
            "title_match": 0.92,
            "company_match": 0.85,
            "recency_of_hire": 0.80,
            "ai_experience": 0.95,
        }),
        "_added_days_ago": 21,
    },
    # --- REPLIED stage ---
    {
        "first_name": "Anna",
        "last_name": "Bergström",
        "title": "VP of AI & Automation",
        "role_type": RoleType.ai_lead,
        "firm": "EQT",
        "_remove_linkedin": "https://www.linkedin.com/in/annabergstrom/",
        "email": "anna.bergstrom@example.com",
        "location": "Stockholm, Sweden",
        "headline": "AI leader driving portfolio transformation",
        "source": "linkedin_people_search",
        "relevance_score": 0.91,
        "status": ProspectStatus.replied,
        "hired_date": now - timedelta(days=60),
        "summary": "M.Sc. AI from Chalmers. Joined EQT 2 months ago from McKinsey QuantumBlack. Replied positively to our first outreach.",
        "dossier": "# Anna Bergström — EQT\n\n## Background\n- M.Sc. Artificial Intelligence, Chalmers University of Technology\n- McKinsey QuantumBlack alumna\n\n## Career\n- **VP of AI & Automation, EQT** (Dec 2025 – Present)\n- **Senior Data Scientist, McKinsey QuantumBlack** (2021–2025)\n\n## Key Signals\n- New in role — 2 months in, actively evaluating vendors\n- EQT is the largest Nordic PE firm (€232B AUM)\n- QuantumBlack background = understands AI implementation deeply\n- Likely scoping execution partners right now",
        "education": json.dumps([
            {"school": "Chalmers University of Technology", "degree": "M.Sc.", "field": "Artificial Intelligence", "start_date": "2017", "end_date": "2019"},
        ]),
        "experience": json.dumps([
            {"title": "VP of AI & Automation", "company": "EQT", "start_date": "Dec 2025"},
            {"title": "Senior Data Scientist", "company": "McKinsey QuantumBlack", "start_date": "2021", "end_date": "2025"},
        ]),
        "score_breakdown": json.dumps({
            "education_match": 0.90,
            "title_match": 0.95,
            "company_match": 1.0,
            "recency_of_hire": 1.0,
            "ai_experience": 0.88,
        }),
        "_added_days_ago": 18,
    },
    # --- SENT stage ---
    {
        "first_name": "Erik",
        "last_name": "Lindqvist",
        "title": "Chief Data Officer",
        "role_type": RoleType.cdo,
        "firm": "Nordic Capital",
        "_remove_linkedin": "https://www.linkedin.com/in/eriklindqvist/",
        "email": "erik.lindqvist@example.com",
        "location": "Stockholm, Sweden",
        "headline": "Driving data-driven decision making in PE",
        "source": "linkedin_jobs",
        "relevance_score": 0.87,
        "status": ProspectStatus.sent,
        "hired_date": now - timedelta(days=180),
        "summary": "PhD Statistics from Stockholm University. 6 months into CDO role at Nordic Capital. Previously head of analytics at Klarna.",
        "dossier": "# Erik Lindqvist — Nordic Capital\n\n## Background\n- PhD Statistics, Stockholm University\n\n## Career\n- **CDO, Nordic Capital** (Aug 2025 – Present)\n- **Head of Analytics, Klarna** (2019–2025)\n\n## Key Signals\n- 6 months in — past initial onboarding, now scoping vendors\n- Nordic Capital has €22B AUM\n- Healthcare + tech portfolio = high AI potential",
        "education": json.dumps([
            {"school": "Stockholm University", "degree": "PhD", "field": "Statistics", "start_date": "2014", "end_date": "2019"},
        ]),
        "experience": json.dumps([
            {"title": "Chief Data Officer", "company": "Nordic Capital", "start_date": "Aug 2025"},
            {"title": "Head of Analytics", "company": "Klarna", "start_date": "2019", "end_date": "2025"},
        ]),
        "score_breakdown": json.dumps({
            "education_match": 0.80,
            "title_match": 0.90,
            "company_match": 0.95,
            "recency_of_hire": 0.75,
            "ai_experience": 0.80,
        }),
        "_added_days_ago": 14,
    },
    # --- APPROVED stage (waiting to send) ---
    {
        "first_name": "Frederik",
        "last_name": "Skjødt",
        "title": "Head of Portfolio Analytics",
        "role_type": RoleType.head_of_analytics,
        "firm": "Polaris",
        "_remove_linkedin": "https://www.linkedin.com/in/frederikskjodt/",
        "email": "frederik.skjodt@example.com",
        "location": "Copenhagen, Denmark",
        "headline": "Analytics-driven value creation",
        "source": "linkedin_people_search",
        "relevance_score": 0.68,
        "status": ProspectStatus.approved,
        "summary": "Been at Polaris for a year. More analytics than AI focused. Moderate fit but worth outreach.",
        "dossier": "# Frederik Skjødt — Polaris\n\n## Background\n- M.Sc. Business Analytics, CBS\n\n## Career\n- **Head of Portfolio Analytics, Polaris** (Feb 2025 – Present)\n- **Analytics Manager, Maersk** (2019–2025)\n\n## Key Signals\n- 1 year in role — established but still building\n- Polaris has €3B AUM, strong Danish industrial portfolio\n- Analytics focus — AI could be a natural expansion",
        "score_breakdown": json.dumps({
            "education_match": 0.55,
            "title_match": 0.70,
            "company_match": 0.75,
            "recency_of_hire": 0.50,
            "ai_experience": 0.55,
        }),
        "_added_days_ago": 10,
    },
    # --- DRAFTED stage (pending approval) ---
    {
        "first_name": "Sonja",
        "last_name": "Horn",
        "title": "Head of Data Science & AI",
        "role_type": RoleType.ai_lead,
        "firm": "Fidelio Capital",
        "_remove_linkedin": "https://www.linkedin.com/in/sonjahorn/",
        "email": "sonja.horn@example.com",
        "location": "Stockholm, Sweden",
        "headline": "Building AI capabilities across PE portfolio companies",
        "source": "linkedin_people_search",
        "relevance_score": 0.94,
        "status": ProspectStatus.drafted,
        "hired_date": now - timedelta(days=90),
        "summary": "M.Sc. Machine Learning from KTH. Previously Data Science Lead at EQT, now driving AI transformation at Fidelio Capital's portfolio. Perfect Amida target — new in role, needs execution partners.",
        "dossier": "# Sonja Horn — Fidelio Capital\n\n## Background\n- M.Sc. Machine Learning, KTH Royal Institute of Technology (2018)\n- B.Sc. Computer Science, Uppsala University (2016)\n\n## Career\n- **Head of Data Science & AI, Fidelio Capital** (Nov 2025 – Present)\n  - Hired to build central AI/data capability across portfolio\n  - Reporting directly to Managing Partner\n- **Data Science Lead, EQT** (2020–2025)\n  - Led 8-person data science team\n  - Built ML models for deal sourcing and portfolio monitoring\n  - Shipped NLP pipeline processing 50K+ documents/month\n\n## Key Signals\n- New hire (<4 months) — actively building team and vendor relationships\n- Fidelio expanding into AI-driven value creation\n- Previously at EQT — understands PE operating model deeply\n- Posted on LinkedIn about \"looking for execution partners in AI\"\n\n## Talking Points\n- Reference EQT's AI journey and how Amida complements internal teams\n- Fidelio's portfolio companies in industrials could benefit from predictive maintenance\n- Offer a quick portfolio AI readiness assessment as conversation starter",
        "education": json.dumps([
            {"school": "KTH Royal Institute of Technology", "degree": "M.Sc.", "field": "Machine Learning", "start_date": "2016", "end_date": "2018"},
            {"school": "Uppsala University", "degree": "B.Sc.", "field": "Computer Science", "start_date": "2013", "end_date": "2016"},
        ]),
        "experience": json.dumps([
            {"title": "Head of Data Science & AI", "company": "Fidelio Capital", "start_date": "Nov 2025", "end_date": None, "description": "Building central AI/data capability across portfolio companies."},
            {"title": "Data Science Lead", "company": "EQT", "start_date": "2020", "end_date": "2025", "description": "Led 8-person DS team. Built ML models for deal sourcing and portfolio monitoring."},
            {"title": "Data Scientist", "company": "Spotify", "start_date": "2018", "end_date": "2020", "description": "Recommendation systems and A/B testing."},
        ]),
        "score_breakdown": json.dumps({
            "education_match": 0.95,
            "title_match": 0.98,
            "company_match": 0.90,
            "recency_of_hire": 1.0,
            "ai_experience": 0.92,
        }),
        "_added_days_ago": 7,
    },
    # --- READY stage (researched, needs draft) ---
    {
        "first_name": "Katrine",
        "last_name": "Møller",
        "title": "Data & Analytics Lead",
        "role_type": RoleType.data_lead,
        "firm": "Axcel",
        "_remove_linkedin": "https://www.linkedin.com/in/katrinemoller/",
        "email": "katrine.moller@example.com",
        "location": "Copenhagen, Denmark",
        "headline": "Building data capabilities in Nordic PE",
        "source": "linkedin_jobs",
        "relevance_score": 0.82,
        "status": ProspectStatus.drafted,
        "hired_date": now - timedelta(days=45),
        "summary": "M.Sc. from DTU. Previously at Novo Nordisk in data engineering. Solid technical profile.",
        "dossier": "# Katrine Møller — Axcel\n\n## Background\n- M.Sc. Data Engineering, DTU (Technical University of Denmark)\n\n## Career\n- **Data & Analytics Lead, Axcel** (Jan 2026 – Present)\n- **Senior Data Engineer, Novo Nordisk** (2020–2025)\n\n## Key Signals\n- 6 weeks into new role\n- Axcel has strong tech portfolio (€4B AUM)\n- Coming from pharma data engineering — will need AI/ML execution support",
        "education": json.dumps([
            {"school": "DTU (Technical University of Denmark)", "degree": "M.Sc.", "field": "Data Engineering", "start_date": "2016", "end_date": "2018"},
        ]),
        "experience": json.dumps([
            {"title": "Data & Analytics Lead", "company": "Axcel", "start_date": "Jan 2026"},
            {"title": "Senior Data Engineer", "company": "Novo Nordisk", "start_date": "2020", "end_date": "2025"},
        ]),
        "score_breakdown": json.dumps({
            "education_match": 0.78,
            "title_match": 0.85,
            "company_match": 0.80,
            "recency_of_hire": 0.95,
            "ai_experience": 0.70,
        }),
        "_added_days_ago": 5,
    },
    # --- RESEARCHING stage ---
    {
        "first_name": "Magnus",
        "last_name": "Dahl",
        "title": "Head of Digital & AI",
        "role_type": RoleType.ai_lead,
        "firm": "Altor",
        "_remove_linkedin": "https://www.linkedin.com/in/magnusdahl/",
        "location": "Stockholm, Sweden",
        "headline": "Digital transformation in private equity",
        "source": "google_news",
        "relevance_score": 0.78,
        "status": ProspectStatus.researching,
        "hired_date": now - timedelta(days=30),
        "summary": "New hire at Altor. Background in consulting (BCG). Less technical than ideal but in the right role at a good firm.",
        "_added_days_ago": 3,
    },
    # --- NEW stage ---
    {
        "first_name": "Lisa",
        "last_name": "Johansson",
        "title": "AI Strategy Lead",
        "role_type": RoleType.ai_lead,
        "firm": "Verdane",
        "_remove_linkedin": "https://www.linkedin.com/in/lisajohansson/",
        "location": "Oslo, Norway",
        "headline": "AI strategy for growth equity",
        "source": "linkedin_jobs",
        "relevance_score": 0.85,
        "status": ProspectStatus.new,
        "hired_date": now - timedelta(days=14),
        "summary": "Just started at Verdane 2 weeks ago. Previously at BCG Gamma. Very fresh — ideal timing for outreach.",
        "_added_days_ago": 2,
    },
    {
        "first_name": "Olav",
        "last_name": "Henriksen",
        "title": "CTO",
        "role_type": RoleType.cto,
        "firm": "Summa Equity",
        "_remove_linkedin": "https://www.linkedin.com/in/olavhenriksen/",
        "email": "olav.henriksen@example.com",
        "location": "Oslo, Norway",
        "headline": "Technology & sustainability in PE",
        "source": "linkedin_people_search",
        "relevance_score": 0.72,
        "status": ProspectStatus.new,
        "summary": "CTO at impact-focused PE firm. Generalist tech leader, not AI-specific. Medium relevance but Summa's sustainability focus is interesting.",
        "_added_days_ago": 1,
    },
]


def seed():
    init_db()
    with get_session() as session:
        existing = session.exec(select(Prospect)).all()
        if existing:
            print(f"Already have {len(existing)} prospects. Skipping seed.")
            return

        for p_data in PROSPECTS:
            firm_name = p_data.pop("firm", None)
            added_days_ago = p_data.pop("_added_days_ago", 0)
            p_data.pop("_remove_linkedin", None)
            firm_id = get_firm_id(session, firm_name) if firm_name else None

            added_at = now - timedelta(days=added_days_ago)

            prospect = Prospect(
                pe_firm_id=firm_id,
                full_name=f"{p_data['first_name']} {p_data['last_name']}",
                created_at=added_at,
                updated_at=added_at,
                **p_data,
            )
            session.add(prospect)
            session.flush()

            # Log: prospect discovered
            session.add(ActivityLog(
                prospect_id=prospect.id,
                action="prospect_added",
                details=f"Source: {prospect.source}",
                created_at=added_at,
            ))

            # For researching+, log the research start
            if prospect.status not in (ProspectStatus.new,):
                research_at = added_at + timedelta(hours=6)
                session.add(ActivityLog(
                    prospect_id=prospect.id,
                    action="research_started",
                    details="Enrichment via Proxycurl + Hunter.io",
                    created_at=research_at,
                ))

            # For ready+ with dossier, log dossier built
            if prospect.dossier and prospect.status not in (ProspectStatus.new, ProspectStatus.researching):
                dossier_at = added_at + timedelta(days=1)
                session.add(ActivityLog(
                    prospect_id=prospect.id,
                    action="dossier_built",
                    details="AI research dossier generated",
                    created_at=dossier_at,
                ))

            # Drafted+ : create draft and log it
            if prospect.status in (
                ProspectStatus.drafted, ProspectStatus.approved,
                ProspectStatus.sent, ProspectStatus.replied,
                ProspectStatus.meeting,
            ):
                draft_at = added_at + timedelta(days=2)
                is_approved = prospect.status != ProspectStatus.drafted

                draft = OutreachDraft(
                    prospect_id=prospect.id,
                    channel=Channel.email,
                    sequence_step=1,
                    subject=f"AI execution for {firm_name}'s portfolio",
                    body=f"Hi {prospect.first_name},\n\nCongratulations on joining {firm_name} as {prospect.title} — exciting move!\n\nAt Amida AI, we help PE firms like {firm_name} turn AI strategy into production systems across portfolio companies. We embed with portcos to ship ML models that drive measurable value — not just proof of concepts.\n\nWould you have 20 minutes next week for a quick call? I'd love to hear about {firm_name}'s AI vision and share how we might help.\n\nBest regards,\nFelipe",
                    approved=True if is_approved else None,
                    approved_at=draft_at + timedelta(days=1) if is_approved else None,
                    created_at=draft_at,
                )
                session.add(draft)

                session.add(ActivityLog(
                    prospect_id=prospect.id,
                    action="draft_created",
                    channel=Channel.email,
                    details=f"Step 1 email drafted",
                    created_at=draft_at,
                ))

                if is_approved:
                    approve_at = draft_at + timedelta(days=1)
                    session.add(ActivityLog(
                        prospect_id=prospect.id,
                        action="draft_approved",
                        channel=Channel.email,
                        details="Step 1 approved",
                        created_at=approve_at,
                    ))

            # Sent+: log the send
            if prospect.status in (ProspectStatus.sent, ProspectStatus.replied, ProspectStatus.meeting):
                send_at = added_at + timedelta(days=4)
                session.add(ActivityLog(
                    prospect_id=prospect.id,
                    action="email_sent",
                    channel=Channel.email,
                    details="Step 1 sent via Smartlead",
                    created_at=send_at,
                ))

            # Replied+: log the reply
            if prospect.status in (ProspectStatus.replied, ProspectStatus.meeting):
                reply_at = added_at + timedelta(days=7)
                session.add(ActivityLog(
                    prospect_id=prospect.id,
                    action="reply_received",
                    channel=Channel.email,
                    details=f"{prospect.first_name} replied positively",
                    created_at=reply_at,
                ))

            # Meeting: log meeting booked
            if prospect.status == ProspectStatus.meeting:
                meeting_at = added_at + timedelta(days=9)
                session.add(ActivityLog(
                    prospect_id=prospect.id,
                    action="meeting_booked",
                    details="30 min intro call scheduled",
                    created_at=meeting_at,
                ))

        # Add Sonja's personalized pending draft (the one awaiting approval)
        sonja = session.exec(select(Prospect).where(Prospect.full_name == "Sonja Horn")).first()
        if sonja:
            session.add(OutreachDraft(
                prospect_id=sonja.id,
                channel=Channel.email,
                sequence_step=1,
                subject="AI execution for Fidelio Capital's portfolio companies",
                body="Hi Sonja,\n\nCongratulations on joining Fidelio Capital as Head of Data Science & AI — exciting move from EQT!\n\nI'm reaching out because we help PE firms like Fidelio turn AI strategy into production systems across portfolio companies. Given your background building ML pipelines at EQT, I think you'd appreciate our approach: we embed with portfolio companies to ship AI that actually works, not just proof of concepts.\n\nA few examples relevant to Fidelio's industrial portfolio:\n- Predictive maintenance models (30% reduction in unplanned downtime)\n- NLP-powered due diligence automation (80% faster document review)\n- Customer churn prediction for SaaS portfolio companies\n\nWould you have 20 minutes next week for a quick call? I'd love to hear about Fidelio's AI vision and share how we might help.\n\nBest regards,\nFelipe",
                created_at=now - timedelta(hours=3),
            ))

        # Add Katrine's LinkedIn pending draft
        katrine = session.exec(select(Prospect).where(Prospect.full_name == "Katrine Møller")).first()
        if katrine:
            session.add(OutreachDraft(
                prospect_id=katrine.id,
                channel=Channel.linkedin,
                sequence_step=1,
                body="Hi Katrine, congrats on the new role at Axcel! Coming from Novo Nordisk's data team, you probably know the gap between data strategy and execution. At Amida AI we bridge exactly that for PE portfolios. Would love to connect and share some ideas relevant to Axcel's tech portfolio.",
                created_at=now - timedelta(hours=1),
            ))

        session.commit()
        total = len(session.exec(select(Prospect)).all())
        drafts = len(session.exec(select(OutreachDraft)).all())
        activity = len(session.exec(select(ActivityLog)).all())
        print(f"Seeded {total} prospects, {drafts} drafts, {activity} activity entries.")


if __name__ == "__main__":
    seed()
