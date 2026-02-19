"""Multi-step email sequence orchestration.

Manages progression through a 4-step email sequence:
  Step 1: First touch → Step 2: Follow-up (3 days) →
  Step 3: Case study (5 days) → Step 4: Breakup (7 days)

Checks for replies via Smartlead and auto-composes follow-ups
that go through the approval queue before sending.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlmodel import select

from amida_agent.config import settings
from amida_agent.database import get_session
from amida_agent.models import (
    ActivityLog,
    Channel,
    OutreachDraft,
    Prospect,
    ProspectStatus,
)

logger = logging.getLogger(__name__)

MAX_SEQUENCE_STEPS = 4


def check_sequence_progression() -> dict:
    """Daily job: progress sequences for all sent prospects.

    For each prospect with status=sent whose latest email step < 4:
      1. Check if enough days have passed since last send
      2. Check Smartlead for replies → if replied, stop sequence
      3. If no reply and delay elapsed → compose next step
      4. Save new draft (pending approval or auto-approved)

    Returns summary dict with counts.
    """
    from amida_agent.ai.composer import compose_email
    from amida_agent.outreach.email_sender import fetch_lead_status

    step_delays = _get_step_delays()
    composed = 0
    replied = 0
    skipped = 0

    with get_session() as session:
        # Find all prospects with status=sent
        prospects = session.exec(
            select(Prospect).where(Prospect.status == ProspectStatus.sent)
        ).all()

        for prospect in prospects:
            # Get the latest approved email draft for this prospect
            latest_draft = session.exec(
                select(OutreachDraft)
                .where(OutreachDraft.prospect_id == prospect.id)
                .where(OutreachDraft.channel == Channel.email)
                .where(OutreachDraft.approved.is_(True))
                .order_by(OutreachDraft.sequence_step.desc())
            ).first()

            if not latest_draft:
                skipped += 1
                continue

            # Already at max steps
            if latest_draft.sequence_step >= MAX_SEQUENCE_STEPS:
                skipped += 1
                continue

            # Check if there's already a pending draft for the next step
            next_step = latest_draft.sequence_step + 1
            pending_next = session.exec(
                select(OutreachDraft)
                .where(OutreachDraft.prospect_id == prospect.id)
                .where(OutreachDraft.channel == Channel.email)
                .where(OutreachDraft.sequence_step == next_step)
                .where(OutreachDraft.approved.is_(None))
            ).first()

            if pending_next:
                skipped += 1
                continue

            # Check timing
            days_since = _days_since_last_send(prospect.id, session)
            delay_needed = step_delays[latest_draft.sequence_step - 1] if latest_draft.sequence_step <= len(step_delays) else 7

            if days_since < delay_needed:
                skipped += 1
                continue

            # Check Smartlead for replies
            if latest_draft.smartlead_campaign_id and latest_draft.smartlead_lead_id:
                try:
                    status = fetch_lead_status(
                        latest_draft.smartlead_campaign_id,
                        latest_draft.smartlead_lead_id,
                    )
                    if _has_reply(status):
                        handle_reply(prospect.id, session=session)
                        replied += 1
                        continue
                except Exception:
                    logger.exception("Failed to fetch Smartlead status for prospect %d", prospect.id)

            # Compose next step
            if not prospect.dossier or not settings.anthropic_api_key:
                skipped += 1
                continue

            previous_body = latest_draft.edited_body or latest_draft.body
            previous_email = f"Subject: {latest_draft.subject}\n\n{previous_body}"

            try:
                subject, body = compose_email(
                    prospect.dossier,
                    sequence_step=next_step,
                    previous_email=previous_email,
                )
            except Exception:
                logger.exception("Failed to compose step %d for prospect %d", next_step, prospect.id)
                skipped += 1
                continue

            # Create new draft
            new_draft = OutreachDraft(
                prospect_id=prospect.id,
                channel=Channel.email,
                sequence_step=next_step,
                subject=subject,
                body=body,
                smartlead_campaign_id=latest_draft.smartlead_campaign_id,
                smartlead_lead_id=latest_draft.smartlead_lead_id,
            )

            # Auto-approve if configured
            if settings.auto_approve_followups:
                new_draft.approved = True
                new_draft.approved_at = datetime.utcnow()

            session.add(new_draft)
            session.add(ActivityLog(
                prospect_id=prospect.id,
                action="followup_composed",
                channel=Channel.email,
                details=json.dumps({"step": next_step, "auto_approved": settings.auto_approve_followups}),
            ))
            composed += 1

        session.commit()

    # Notify if there are new drafts to review
    if composed > 0 and not settings.auto_approve_followups:
        from amida_agent.notifications.notifier import notify_needs_approval
        notify_needs_approval(composed)

    summary = {"composed": composed, "replied": replied, "skipped": skipped}
    logger.info("Sequence progression complete: %s", summary)
    return summary


def handle_reply(prospect_id: int, session=None) -> None:
    """Mark a prospect as replied and stop the sequence."""
    own_session = session is None

    if own_session:
        session = get_session().__enter__()

    try:
        prospect = session.get(Prospect, prospect_id)
        if not prospect:
            logger.error("Prospect %d not found", prospect_id)
            return

        prospect.status = ProspectStatus.replied
        prospect.updated_at = datetime.utcnow()

        session.add(ActivityLog(
            prospect_id=prospect_id,
            action="reply_received",
            channel=Channel.email,
            details=json.dumps({"previous_status": "sent"}),
        ))

        if own_session:
            session.commit()

        logger.info("Prospect %d marked as replied", prospect_id)

        # Notify
        from amida_agent.notifications.notifier import notify_reply
        notify_reply(prospect.full_name)

    finally:
        if own_session:
            session.__exit__(None, None, None)


def get_sequence_status(prospect_id: int) -> dict:
    """Get the current sequence status for a prospect.

    Returns dict with current_step, days_since_last_send, has_reply, max_steps.
    """
    with get_session() as session:
        prospect = session.get(Prospect, prospect_id)
        if not prospect:
            return {}

        latest_draft = session.exec(
            select(OutreachDraft)
            .where(OutreachDraft.prospect_id == prospect_id)
            .where(OutreachDraft.channel == Channel.email)
            .where(OutreachDraft.approved.is_(True))
            .order_by(OutreachDraft.sequence_step.desc())
        ).first()

        current_step = latest_draft.sequence_step if latest_draft else 0
        days_since = _days_since_last_send(prospect_id, session)

        return {
            "prospect_id": prospect_id,
            "prospect_name": prospect.full_name,
            "status": prospect.status.value,
            "current_step": current_step,
            "max_steps": MAX_SEQUENCE_STEPS,
            "days_since_last_send": days_since,
            "has_reply": prospect.status == ProspectStatus.replied,
        }


def sync_smartlead_statuses() -> dict:
    """Sync reply/open status from Smartlead for all active campaigns.

    Called periodically to detect replies that happened outside
    the sequence progression check.
    """
    from amida_agent.outreach.email_sender import fetch_lead_status

    if not settings.smartlead_api_key:
        return {"synced": 0, "replies": 0}

    synced = 0
    replies = 0

    with get_session() as session:
        # Find all sent prospects with Smartlead tracking
        drafts = session.exec(
            select(OutreachDraft)
            .where(OutreachDraft.smartlead_campaign_id.isnot(None))
            .where(OutreachDraft.smartlead_lead_id.isnot(None))
            .where(OutreachDraft.approved.is_(True))
        ).all()

        # Deduplicate by prospect
        seen_prospects = set()
        for draft in drafts:
            if draft.prospect_id in seen_prospects:
                continue
            seen_prospects.add(draft.prospect_id)

            prospect = session.get(Prospect, draft.prospect_id)
            if not prospect or prospect.status != ProspectStatus.sent:
                continue

            try:
                status = fetch_lead_status(draft.smartlead_campaign_id, draft.smartlead_lead_id)
                synced += 1

                if _has_reply(status):
                    handle_reply(prospect.id, session=session)
                    replies += 1
            except Exception:
                logger.exception("Failed to sync Smartlead status for prospect %d", prospect.id)

        session.commit()

    summary = {"synced": synced, "replies": replies}
    logger.info("Smartlead status sync complete: %s", summary)
    return summary


def _days_since_last_send(prospect_id: int, session) -> int:
    """Calculate days since the last approved email was sent for a prospect."""
    latest = session.exec(
        select(OutreachDraft)
        .where(OutreachDraft.prospect_id == prospect_id)
        .where(OutreachDraft.channel == Channel.email)
        .where(OutreachDraft.approved.is_(True))
        .order_by(OutreachDraft.approved_at.desc())
    ).first()

    if not latest or not latest.approved_at:
        return 999  # No previous send

    delta = datetime.utcnow() - latest.approved_at
    return delta.days


def _has_reply(smartlead_status: dict) -> bool:
    """Check if a Smartlead lead status indicates a reply."""
    if not smartlead_status:
        return False
    # Smartlead uses various fields; check common ones
    return bool(
        smartlead_status.get("replied")
        or smartlead_status.get("reply_count", 0) > 0
        or smartlead_status.get("is_replied")
    )


def _get_step_delays() -> list[int]:
    """Parse sequence step delays from config."""
    raw = settings.sequence_step_delays
    try:
        return [int(d.strip()) for d in raw.split(",")]
    except (ValueError, AttributeError):
        return [3, 5, 7]
