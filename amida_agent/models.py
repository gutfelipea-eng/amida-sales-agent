from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


# --- Enums ---

class ProspectStatus(str, Enum):
    new = "new"
    researching = "researching"
    ready = "ready"            # dossier built, awaiting draft
    drafted = "drafted"        # outreach drafted, awaiting approval
    approved = "approved"      # approved, ready to send
    sent = "sent"              # first touch sent
    replied = "replied"
    meeting = "meeting"        # meeting booked
    rejected = "rejected"      # not a fit
    paused = "paused"


class Channel(str, Enum):
    email = "email"
    linkedin = "linkedin"


class RoleType(str, Enum):
    ai_lead = "ai_lead"
    data_lead = "data_lead"
    cto = "cto"
    cdo = "cdo"
    head_of_analytics = "head_of_analytics"
    other = "other"


# --- Models ---

class PEFirm(SQLModel, table=True):
    __tablename__ = "pe_firms"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    website: str = ""
    linkedin_url: str = ""
    country: str = ""
    hq_city: str = ""
    aum_billion_eur: Optional[float] = None
    portfolio_count: Optional[int] = None
    sectors: str = ""  # comma-separated
    notes: str = ""
    monitoring_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Prospect(SQLModel, table=True):
    __tablename__ = "prospects"

    id: Optional[int] = Field(default=None, primary_key=True)
    pe_firm_id: Optional[int] = Field(default=None, foreign_key="pe_firms.id")
    first_name: str = ""
    last_name: str = ""
    full_name: str = Field(index=True)
    title: str = ""
    role_type: RoleType = RoleType.other
    linkedin_url: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    location: str = ""
    education: str = ""  # JSON string of education entries
    experience: str = ""  # JSON string of experience entries
    skills: str = ""  # comma-separated
    headline: str = ""
    summary: str = ""
    profile_photo_url: str = ""

    # Scoring
    relevance_score: float = 0.0  # 0-1
    score_breakdown: str = ""  # JSON string

    # Research
    dossier: str = ""  # markdown dossier
    company_context: str = ""  # JSON string

    # State
    status: ProspectStatus = ProspectStatus.new
    source: str = ""  # how we found them
    hired_date: Optional[datetime] = None  # when they joined current role

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OutreachDraft(SQLModel, table=True):
    __tablename__ = "outreach_drafts"

    id: Optional[int] = Field(default=None, primary_key=True)
    prospect_id: int = Field(foreign_key="prospects.id", index=True)
    channel: Channel = Channel.email
    sequence_step: int = 1  # 1=first touch, 2=follow-up, etc.
    subject: str = ""
    body: str = ""
    approved: Optional[bool] = None  # None=pending, True=approved, False=rejected
    approved_at: Optional[datetime] = None
    edited_body: Optional[str] = None  # if Felipe edits before approving
    rejection_reason: str = ""

    # Smartlead tracking
    smartlead_campaign_id: Optional[str] = None
    smartlead_lead_id: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ActivityLog(SQLModel, table=True):
    __tablename__ = "activity_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    prospect_id: Optional[int] = Field(default=None, foreign_key="prospects.id")
    action: str = ""  # e.g. "email_sent", "replied", "meeting_booked", "researched"
    channel: Optional[Channel] = None
    details: str = ""  # JSON string with extra context
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SearchQuery(SQLModel, table=True):
    __tablename__ = "search_queries"

    id: Optional[int] = Field(default=None, primary_key=True)
    query_type: str = ""  # "linkedin_jobs", "linkedin_people", "google_news"
    query_text: str = ""
    pe_firm_id: Optional[int] = Field(default=None, foreign_key="pe_firms.id")
    results_count: int = 0
    last_run_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
