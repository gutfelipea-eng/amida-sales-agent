from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import select

from amida_agent.database import get_session
from amida_agent.models import (
    ActivityLog,
    Channel,
    OutreachDraft,
    PEFirm,
    Prospect,
    ProspectStatus,
)
from amida_agent.web.deps import templates

router = APIRouter()


def _get_queue_context(session):
    """Shared query logic for the approval queue."""
    drafts = session.exec(
        select(OutreachDraft)
        .where(OutreachDraft.approved.is_(None))
        .order_by(OutreachDraft.created_at.asc())
    ).all()

    prospect_ids = {d.prospect_id for d in drafts}
    prospects = {}
    firms = {}
    if prospect_ids:
        for p in session.exec(select(Prospect).where(Prospect.id.in_(prospect_ids))).all():
            prospects[p.id] = p
        firm_ids = {p.pe_firm_id for p in prospects.values() if p.pe_firm_id}
        if firm_ids:
            for f in session.exec(select(PEFirm).where(PEFirm.id.in_(firm_ids))).all():
                firms[f.id] = f.name

    return drafts, prospects, firms


@router.get("/")
def approval_queue(request: Request):
    with get_session() as session:
        drafts, prospects, firms = _get_queue_context(session)

    return templates.TemplateResponse("approve.html", {
        "request": request,
        "drafts": drafts,
        "prospects": prospects,
        "firms": firms,
        "pending_approval": len(drafts),
    })


@router.post("/{draft_id}/approve")
def approve_draft(
    request: Request,
    draft_id: int,
    edited_subject: str = Form(None),
    edited_body: str = Form(None),
):
    with get_session() as session:
        draft = session.get(OutreachDraft, draft_id)
        if not draft:
            return HTMLResponse("<p>Draft not found</p>", status_code=404)

        draft.approved = True
        draft.approved_at = datetime.utcnow()
        if edited_body and edited_body.strip():
            draft.edited_body = edited_body.strip()
        if edited_subject and edited_subject.strip():
            draft.subject = edited_subject.strip()
        draft.updated_at = datetime.utcnow()

        prospect = session.get(Prospect, draft.prospect_id)
        if prospect and prospect.status == ProspectStatus.drafted:
            prospect.status = ProspectStatus.approved
            prospect.updated_at = datetime.utcnow()

        session.add(ActivityLog(
            prospect_id=draft.prospect_id,
            action="draft_approved",
            channel=draft.channel,
            details=f"Step {draft.sequence_step} approved",
        ))
        session.commit()

        # Send macOS notification
        from amida_agent.notifications.notifier import notify
        notify(
            "Draft Approved",
            f"{prospect.full_name} — step {draft.sequence_step} ready to send"
            if prospect else f"Draft {draft_id} approved",
        )

        # Trigger send for email channel
        if draft.channel == Channel.email:
            from amida_agent.outreach.email_sender import send_approved_draft
            send_approved_draft(draft.id)

        drafts, prospects, firms = _get_queue_context(session)

    return templates.TemplateResponse("partials/approval_list.html", {
        "request": request,
        "drafts": drafts,
        "prospects": prospects,
        "firms": firms,
    })


@router.post("/{draft_id}/reject")
def reject_draft(request: Request, draft_id: int, reason: str = Form("")):
    with get_session() as session:
        draft = session.get(OutreachDraft, draft_id)
        if not draft:
            return HTMLResponse("<p>Draft not found</p>", status_code=404)

        draft.approved = False
        draft.rejection_reason = reason
        draft.updated_at = datetime.utcnow()

        prospect = session.get(Prospect, draft.prospect_id)
        if prospect and prospect.status == ProspectStatus.drafted:
            prospect.status = ProspectStatus.rejected
            prospect.updated_at = datetime.utcnow()

        session.add(ActivityLog(
            prospect_id=draft.prospect_id,
            action="draft_rejected",
            channel=draft.channel,
            details=reason or "No reason given",
        ))
        session.commit()

        drafts, prospects, firms = _get_queue_context(session)

    return templates.TemplateResponse("partials/approval_list.html", {
        "request": request,
        "drafts": drafts,
        "prospects": prospects,
        "firms": firms,
    })


@router.post("/{draft_id}/regenerate")
def regenerate_draft(request: Request, draft_id: int):
    """Reject current draft and generate a new one via AI."""
    from amida_agent.ai.composer import compose_email
    from amida_agent.config import settings

    with get_session() as session:
        draft = session.get(OutreachDraft, draft_id)
        if not draft:
            return HTMLResponse("<p>Draft not found</p>", status_code=404)

        prospect = session.get(Prospect, draft.prospect_id)
        if not prospect or not prospect.dossier:
            return HTMLResponse("<p>No dossier available for regeneration</p>", status_code=400)

        if not settings.anthropic_api_key:
            return HTMLResponse("<p>ANTHROPIC_API_KEY not set</p>", status_code=500)

        # Mark old draft as rejected
        draft.approved = False
        draft.rejection_reason = "Regenerated"
        draft.updated_at = datetime.utcnow()

        # Generate new draft
        subject, body = compose_email(prospect.dossier, sequence_step=draft.sequence_step)

        new_draft = OutreachDraft(
            prospect_id=prospect.id,
            channel=draft.channel,
            sequence_step=draft.sequence_step,
            subject=subject,
            body=body,
        )
        session.add(new_draft)

        session.add(ActivityLog(
            prospect_id=prospect.id,
            action="draft_regenerated",
            channel=draft.channel,
            details=f"Step {draft.sequence_step} regenerated",
        ))
        session.commit()

        drafts, prospects_map, firms = _get_queue_context(session)

    return templates.TemplateResponse("partials/approval_list.html", {
        "request": request,
        "drafts": drafts,
        "prospects": prospects_map,
        "firms": firms,
    })
