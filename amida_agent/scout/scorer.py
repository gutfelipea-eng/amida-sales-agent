"""Pre-score discovered leads before spending Proxycurl/Hunter credits.

Two-tier scoring:
  pre_score()      → lightweight gate (title + source signals), threshold 0.40
  dossier_builder.score_relevance() → full score after enrichment, threshold 0.65
"""

import re

from amida_agent.config import settings

# Titles that strongly indicate AI/data leadership
_STRONG_TITLES = [
    "head of ai", "head of data", "head of machine learning",
    "chief data officer", "chief analytics officer", "chief ai officer",
    "vp of ai", "vp of data", "vp data", "vp ai",
    "director of ai", "director of data science", "director of analytics",
    "ai lead", "data science lead", "ml lead",
]

# Titles that partially indicate relevance
_MODERATE_TITLES = [
    "cto", "chief technology officer",
    "head of analytics", "head of engineering",
    "data engineer", "machine learning engineer",
    "data strategy", "digital transformation",
    "partner", "operating partner",  # PE context makes these relevant
]

# AI/data keywords for fuzzy title matching
_AI_KEYWORDS = re.compile(
    r"\b(ai|artificial.intelligence|machine.learning|data.science|"
    r"ml|nlp|deep.learning|analytics|data.platform|data.strategy)\b",
    re.IGNORECASE,
)

# Source quality weights
_SOURCE_WEIGHTS = {
    "people_search": 0.25,   # Direct role lookup — highest quality
    "news_monitor": 0.15,    # News mention — moderate
    "job_monitor": 0.10,     # Hiring signal — indirect
    "manual": 0.20,          # Human-curated
}


def pre_score(
    title: str,
    company: str = "",
    source: str = "",
    has_hiring_signal: bool = False,
    has_news_mention: bool = False,
) -> tuple[float, dict]:
    """Score a raw lead 0-1 based on lightweight signals.

    Returns (score, breakdown) where breakdown maps component names to values:
      title_relevance  0 – 0.40
      source_quality   0 – 0.25
      hiring_signal    0 – 0.20
      news_buzz        0 – 0.15
    """
    breakdown: dict[str, float] = {}

    # --- Title relevance (0-0.40) ---
    title_lower = title.lower().strip()
    title_score = 0.0
    if any(t in title_lower for t in _STRONG_TITLES):
        title_score = 0.40
    elif any(t in title_lower for t in _MODERATE_TITLES):
        title_score = 0.20
    elif _AI_KEYWORDS.search(title_lower):
        title_score = 0.25
    # Seniority bonus (capped at 0.40)
    if any(kw in title_lower for kw in ["head", "chief", "vp", "director", "lead", "partner"]):
        title_score = min(title_score + 0.10, 0.40)
    breakdown["title_relevance"] = round(title_score, 2)

    # --- Source quality (0-0.25) ---
    source_score = _SOURCE_WEIGHTS.get(source, 0.05)
    breakdown["source_quality"] = round(source_score, 2)

    # --- Hiring signal (0-0.20) ---
    hiring_score = 0.20 if has_hiring_signal else 0.0
    breakdown["hiring_signal"] = round(hiring_score, 2)

    # --- News buzz (0-0.15) ---
    news_score = 0.15 if has_news_mention else 0.0
    breakdown["news_buzz"] = round(news_score, 2)

    total = round(min(title_score + source_score + hiring_score + news_score, 1.0), 2)
    return total, breakdown


def should_enrich(score: float) -> bool:
    """Should we spend a Proxycurl credit to enrich this lead?"""
    return score >= settings.enrichment_threshold


def should_notify(score: float) -> bool:
    """Should we send a desktop notification for this lead?"""
    return score >= settings.notification_threshold
