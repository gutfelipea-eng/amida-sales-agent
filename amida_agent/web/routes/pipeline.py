from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import select

from amida_agent.database import get_session
from amida_agent.models import ActivityLog, PEFirm, Prospect, ProspectStatus
from amida_agent.web.deps import templates

router = APIRouter()

PIPELINE_COLUMNS = [
    ("new", "New Leads"),
    ("researching", "Researching"),
    ("ready", "Ready"),
    ("drafted", "Drafted"),
    ("approved", "Approved"),
    ("sent", "Sent"),
    ("replied", "Replied"),
    ("meeting", "Meeting"),
]


def _build_pipeline(session):
    all_prospects = session.exec(select(Prospect)).all()
    firm_ids = {p.pe_firm_id for p in all_prospects if p.pe_firm_id}
    firms = {}
    if firm_ids:
        for f in session.exec(select(PEFirm).where(PEFirm.id.in_(firm_ids))).all():
            firms[f.id] = f.name

    columns = []
    for status_val, label in PIPELINE_COLUMNS:
        prospects = sorted(
            [p for p in all_prospects if p.status == status_val],
            key=lambda p: p.relevance_score,
            reverse=True,
        )
        columns.append({"status": status_val, "label": label, "prospects": prospects})

    return columns, firms


@router.get("/")
def pipeline_view(request: Request):
    with get_session() as session:
        columns, firms = _build_pipeline(session)

    return templates.TemplateResponse("pipeline.html", {
        "request": request,
        "columns": columns,
        "firms": firms,
    })


@router.post("/move")
def move_prospect(request: Request, prospect_id: int = Form(...), status: str = Form(...)):
    """HTMX endpoint: move a prospect to a new pipeline stage."""
    with get_session() as session:
        prospect = session.get(Prospect, prospect_id)
        if not prospect:
            return HTMLResponse("<p>Not found</p>", status_code=404)

        old_status = prospect.status.value
        prospect.status = ProspectStatus(status)
        prospect.updated_at = datetime.utcnow()

        session.add(ActivityLog(
            prospect_id=prospect_id,
            action="pipeline_moved",
            details=f"{old_status} -> {status}",
        ))
        session.commit()

        columns, firms = _build_pipeline(session)

    return templates.TemplateResponse("partials/pipeline_board.html", {
        "request": request,
        "columns": columns,
        "firms": firms,
    })
