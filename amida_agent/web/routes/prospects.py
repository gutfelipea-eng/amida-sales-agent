import json
from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import select

from amida_agent.database import get_session
from amida_agent.models import (
    ActivityLog,
    OutreachDraft,
    PEFirm,
    Prospect,
    ProspectStatus,
)
from amida_agent.web.deps import templates

router = APIRouter()


@router.get("/")
def list_prospects(request: Request, status: str | None = None):
    with get_session() as session:
        query = select(Prospect).order_by(Prospect.relevance_score.desc())
        if status:
            query = query.where(Prospect.status == status)
        prospects = session.exec(query).all()

        firm_ids = {p.pe_firm_id for p in prospects if p.pe_firm_id}
        firms = {}
        if firm_ids:
            for firm in session.exec(select(PEFirm).where(PEFirm.id.in_(firm_ids))).all():
                firms[firm.id] = firm.name

    return templates.TemplateResponse("prospects.html", {
        "request": request,
        "prospects": prospects,
        "firms": firms,
        "current_status": status,
    })


@router.get("/{prospect_id}")
def prospect_detail(request: Request, prospect_id: int):
    with get_session() as session:
        prospect = session.get(Prospect, prospect_id)
        if not prospect:
            return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

        firm = session.get(PEFirm, prospect.pe_firm_id) if prospect.pe_firm_id else None

        # Outreach history
        drafts = session.exec(
            select(OutreachDraft)
            .where(OutreachDraft.prospect_id == prospect_id)
            .order_by(OutreachDraft.created_at.desc())
        ).all()

        # Activity log
        activity = session.exec(
            select(ActivityLog)
            .where(ActivityLog.prospect_id == prospect_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(20)
        ).all()

    # Parse score breakdown
    score_breakdown = {}
    if prospect.score_breakdown:
        try:
            score_breakdown = json.loads(prospect.score_breakdown)
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse education/experience for display
    education = []
    experience = []
    try:
        education = json.loads(prospect.education) if prospect.education else []
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        experience = json.loads(prospect.experience) if prospect.experience else []
    except (json.JSONDecodeError, TypeError):
        pass

    return templates.TemplateResponse("prospect_detail.html", {
        "request": request,
        "prospect": prospect,
        "firm": firm,
        "drafts": drafts,
        "activity": activity,
        "score_breakdown": score_breakdown,
        "education": education,
        "experience": experience,
    })


@router.post("/{prospect_id}/status")
def update_status(request: Request, prospect_id: int, status: str = Form(...)):
    """HTMX endpoint to change prospect status."""
    with get_session() as session:
        prospect = session.get(Prospect, prospect_id)
        if not prospect:
            return HTMLResponse("<p>Not found</p>", status_code=404)

        old_status = prospect.status.value
        prospect.status = ProspectStatus(status)
        prospect.updated_at = datetime.utcnow()

        session.add(ActivityLog(
            prospect_id=prospect_id,
            action="status_changed",
            details=f"{old_status} -> {status}",
        ))
        session.commit()

    return HTMLResponse(
        f'<span class="status-badge {status}">{status}</span>'
    )
