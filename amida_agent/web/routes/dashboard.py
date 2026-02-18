from fastapi import APIRouter, Request
from sqlmodel import func, select

from amida_agent.database import get_session
from amida_agent.models import ActivityLog, OutreachDraft, PEFirm, Prospect, ProspectStatus
from amida_agent.web.deps import templates

router = APIRouter()


def _get_stats(session):
    return {
        "total_firms": session.exec(select(func.count(PEFirm.id))).one(),
        "total_prospects": session.exec(select(func.count(Prospect.id))).one(),
        "pending_approval": session.exec(
            select(func.count(OutreachDraft.id)).where(OutreachDraft.approved.is_(None))
        ).one(),
        "sent_count": session.exec(
            select(func.count(Prospect.id)).where(Prospect.status == ProspectStatus.sent)
        ).one(),
        "replied_count": session.exec(
            select(func.count(Prospect.id)).where(Prospect.status == ProspectStatus.replied)
        ).one(),
        "meeting_count": session.exec(
            select(func.count(Prospect.id)).where(Prospect.status == ProspectStatus.meeting)
        ).one(),
    }


def _get_recent_activity(session, limit=10):
    return session.exec(
        select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
    ).all()


@router.get("/")
@router.get("/dashboard")
def dashboard(request: Request):
    with get_session() as session:
        stats = _get_stats(session)
        recent_activity = _get_recent_activity(session)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        **stats,
        "recent_activity": recent_activity,
    })


@router.get("/dashboard/stats")
def dashboard_stats(request: Request):
    """HTMX partial: refreshes stat cards."""
    with get_session() as session:
        stats = _get_stats(session)

    return templates.TemplateResponse("partials/dashboard_stats.html", {
        "request": request,
        **stats,
    })


@router.get("/dashboard/activity")
def dashboard_activity(request: Request):
    """HTMX partial: refreshes activity feed."""
    with get_session() as session:
        recent_activity = _get_recent_activity(session)

    return templates.TemplateResponse("partials/activity_feed.html", {
        "request": request,
        "recent_activity": recent_activity,
    })
