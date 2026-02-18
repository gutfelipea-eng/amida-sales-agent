"""Build a research dossier for a prospect — markdown summary for AI and human review."""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def build_dossier(
    profile: dict,
    company_context: str | None = None,
    email_info: dict | None = None,
) -> str:
    """Generate a markdown dossier from enriched profile data.

    Args:
        profile: Parsed profile dict from enricher.parse_profile_data()
        company_context: JSON string of company context
        email_info: Dict from email_finder with 'email' and 'score'
    """
    lines = []
    lines.append(f"# {profile.get('full_name', 'Unknown')}")
    lines.append(f"**{profile.get('headline', '')}**")
    lines.append("")

    # Current role
    lines.append("## Current Role")
    lines.append(f"- **Title:** {profile.get('title', 'N/A')}")
    lines.append(f"- **Company:** {profile.get('current_company', 'N/A')}")
    lines.append(f"- **Location:** {profile.get('location', 'N/A')}, {profile.get('country', '')}")
    if profile.get("hired_date"):
        hd = profile["hired_date"]
        if isinstance(hd, str):
            lines.append(f"- **Started:** {hd}")
        else:
            months_ago = (datetime.utcnow() - hd).days // 30
            lines.append(f"- **Started:** {hd.strftime('%B %Y')} ({months_ago} months ago)")
    lines.append("")

    # Experience
    try:
        experiences = json.loads(profile.get("experience_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        experiences = []

    if experiences:
        lines.append("## Experience")
        for exp in experiences[:5]:
            period = ""
            if exp.get("start_year"):
                period = f"{exp['start_year']}"
                if exp.get("start_month"):
                    period = f"{exp['start_month']}/{period}"
                if exp.get("is_current"):
                    period += " – Present"
                elif exp.get("end_year"):
                    end = f"{exp['end_year']}"
                    if exp.get("end_month"):
                        end = f"{exp['end_month']}/{end}"
                    period += f" – {end}"
            lines.append(f"- **{exp.get('title', '')}** at {exp.get('company', '')} ({period})")
            if exp.get("description"):
                desc = exp["description"][:200]
                lines.append(f"  {desc}")
        lines.append("")

    # Education
    try:
        education = json.loads(profile.get("education_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        education = []

    if education:
        lines.append("## Education")
        for edu in education:
            degree_parts = [edu.get("degree", ""), edu.get("field", "")]
            degree = " in ".join(p for p in degree_parts if p)
            year_range = ""
            if edu.get("start_year"):
                year_range = f"{edu['start_year']}"
                if edu.get("end_year"):
                    year_range += f"–{edu['end_year']}"
            lines.append(f"- **{degree}** — {edu.get('school', '')} ({year_range})")
        lines.append("")

    # Skills
    if profile.get("skills"):
        lines.append("## Skills")
        lines.append(profile["skills"])
        lines.append("")

    # Contact
    lines.append("## Contact")
    if email_info:
        lines.append(f"- **Email:** {email_info['email']} (confidence: {email_info.get('score', 'N/A')}%)")
    if profile.get("personal_emails"):
        for e in profile["personal_emails"]:
            lines.append(f"- **Personal email:** {e}")
    if profile.get("phone_numbers"):
        for p in profile["phone_numbers"]:
            lines.append(f"- **Phone:** {p}")
    lines.append("")

    # Company context
    if company_context:
        try:
            ctx = json.loads(company_context)
        except (json.JSONDecodeError, TypeError):
            ctx = {}
        if ctx:
            lines.append("## Company Context")
            lines.append(f"- **Firm:** {ctx.get('firm_name', '')}")
            if ctx.get("aum_billion_eur"):
                lines.append(f"- **AUM:** €{ctx['aum_billion_eur']}B")
            if ctx.get("sectors"):
                lines.append(f"- **Sectors:** {ctx['sectors']}")
            if ctx.get("description"):
                lines.append(f"- **About:** {ctx['description'][:300]}")
            lines.append("")

    # Summary
    if profile.get("summary"):
        lines.append("## LinkedIn Summary")
        lines.append(profile["summary"][:500])
        lines.append("")

    return "\n".join(lines)


def score_relevance(profile: dict, company_context: str | None = None) -> tuple[float, dict]:
    """Score a prospect's relevance 0-1 for Amida's target market.

    Returns (score, breakdown_dict).
    """
    breakdown = {}
    score = 0.0

    title = profile.get("title", "").lower()
    skills = profile.get("skills", "").lower()
    headline = profile.get("headline", "").lower()

    # Title match (0-0.3)
    ai_title_keywords = [
        "ai", "artificial intelligence", "machine learning", "data science",
        "data lead", "head of data", "cdo", "chief data", "ml ", "analytics",
    ]
    title_score = 0.0
    for kw in ai_title_keywords:
        if kw in title or kw in headline:
            title_score = 0.3
            break
    if any(kw in title for kw in ["head", "lead", "director", "vp", "chief"]):
        title_score = min(title_score + 0.05, 0.3)
    breakdown["title_match"] = title_score
    score += title_score

    # Education — ML/DS degrees (0-0.15)
    edu_score = 0.0
    try:
        education = json.loads(profile.get("education_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        education = []
    ml_edu_keywords = ["machine learning", "data science", "artificial intelligence", "computer science", "statistics"]
    for edu in education:
        field = (edu.get("field", "") + " " + edu.get("degree", "")).lower()
        if any(kw in field for kw in ml_edu_keywords):
            edu_score = 0.15
            break
    breakdown["education"] = edu_score
    score += edu_score

    # AI/data skills (0-0.15)
    skill_score = 0.0
    ai_skills = ["python", "machine learning", "deep learning", "tensorflow", "pytorch",
                 "nlp", "data science", "sql", "spark", "aws", "azure", "gcp"]
    matches = sum(1 for s in ai_skills if s in skills)
    if matches >= 4:
        skill_score = 0.15
    elif matches >= 2:
        skill_score = 0.10
    elif matches >= 1:
        skill_score = 0.05
    breakdown["skills"] = skill_score
    score += skill_score

    # Recency of hire (0-0.25) — new hires score highest
    recency_score = 0.0
    if profile.get("hired_date"):
        hd = profile["hired_date"]
        if isinstance(hd, datetime):
            months_ago = (datetime.utcnow() - hd).days / 30
            if months_ago <= 3:
                recency_score = 0.25
            elif months_ago <= 6:
                recency_score = 0.20
            elif months_ago <= 12:
                recency_score = 0.10
            elif months_ago <= 24:
                recency_score = 0.05
    breakdown["recency"] = recency_score
    score += recency_score

    # Company match — is it a known PE firm? (0-0.15)
    company_score = 0.0
    if company_context:
        try:
            ctx = json.loads(company_context)
        except (json.JSONDecodeError, TypeError):
            ctx = {}
        if ctx.get("firm_name"):
            company_score = 0.15
    breakdown["company_match"] = company_score
    score += company_score

    return min(score, 1.0), breakdown
