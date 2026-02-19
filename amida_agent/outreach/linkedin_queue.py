"""Manual LinkedIn action queue.

LinkedIn doesn't allow automated sending. This module provides a task queue
for manual copy-paste actions (connection requests, DMs) that flow through
the same approval queue as email drafts.
"""

import json
import logging
from datetime import datetime

from sqlmodel import select

from amida_agent.database import get_session
from amida_agent.models import (
    ActivityLog,
    Channel,
    OutreachDraft,
    Prospect,
    ProspectStatus,
)

logger = logging.getLogger(__name__)


def queue_connection_request(prospect_id: int) -> int | None:
    """Generate a LinkedIn connection message and save as a draft for approval.

    Returns the new draft ID, or None on failure.
    """
    from amida_agent.ai.composer import compose_linkedin_connection
    from amida_agent.config import settings

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — cannot compose LinkedIn message")
        return None

    with get_session() as session:
        prospect = session.get(Prospect, prospect_id)
        if not prospect or not prospect.dossier:
            logger.error("Prospect %d not found or missing dossier", prospect_id)
            return None

        message = compose_linkedin_connection(prospect.dossier)

        draft = OutreachDraft(
            prospect_id=prospect.id,
            channel=Channel.linkedin,
            sequence_step=1,
            subject="Connection Request",
            body=message,
        )
        session.add(draft)

        session.add(ActivityLog(
            prospect_id=prospect.id,
            action="linkedin_connection_queued",
            channel=Channel.linkedin,
            details=json.dumps({"message_length": len(message)}),
        ))
        session.commit()
        session.refresh(draft)
        draft_id = draft.id

    logger.info("Queued LinkedIn connection request for prospect %d → draft %d", prospect_id, draft_id)
    return draft_id


def queue_linkedin_message(prospect_id: int) -> int | None:
    """Generate a LinkedIn DM and save as a draft for approval.

    Returns the new draft ID, or None on failure.
    """
    from amida_agent.ai.composer import compose_linkedin_message
    from amida_agent.config import settings

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — cannot compose LinkedIn message")
        return None

    with get_session() as session:
        prospect = session.get(Prospect, prospect_id)
        if not prospect or not prospect.dossier:
            logger.error("Prospect %d not found or missing dossier", prospect_id)
            return None

        message = compose_linkedin_message(prospect.dossier)

        draft = OutreachDraft(
            prospect_id=prospect.id,
            channel=Channel.linkedin,
            sequence_step=2,
            subject="LinkedIn Message",
            body=message,
        )
        session.add(draft)

        session.add(ActivityLog(
            prospect_id=prospect.id,
            action="linkedin_message_queued",
            channel=Channel.linkedin,
            details=json.dumps({"message_length": len(message)}),
        ))
        session.commit()
        session.refresh(draft)
        draft_id = draft.id

    logger.info("Queued LinkedIn DM for prospect %d → draft %d", prospect_id, draft_id)
    return draft_id


def get_pending_linkedin_actions() -> list[dict]:
    """Return all approved LinkedIn drafts awaiting manual send.

    Returns list of dicts with draft + prospect info for the dashboard.
    """
    with get_session() as session:
        drafts = session.exec(
            select(OutreachDraft)
            .where(OutreachDraft.channel == Channel.linkedin)
            .where(OutreachDraft.approved.is_(True))
            .where(OutreachDraft.smartlead_lead_id.is_(None))  # not yet marked as sent
            .order_by(OutreachDraft.approved_at.asc())
        ).all()

        actions = []
        for draft in drafts:
            prospect = session.get(Prospect, draft.prospect_id)
            if not prospect:
                continue

            actions.append({
                "draft_id": draft.id,
                "prospect_id": prospect.id,
                "prospect_name": prospect.full_name,
                "prospect_title": prospect.title,
                "linkedin_url": prospect.linkedin_url,
                "action_type": "connection_request" if draft.sequence_step == 1 else "message",
                "message": draft.edited_body or draft.body,
                "approved_at": draft.approved_at,
            })

    return actions


def mark_linkedin_sent(draft_id: int) -> bool:
    """Mark a LinkedIn draft as manually sent.

    Updates prospect status and logs the activity.
    Returns True on success.
    """
    with get_session() as session:
        draft = session.get(OutreachDraft, draft_id)
        if not draft:
            logger.error("Draft %d not found", draft_id)
            return False

        if draft.channel != Channel.linkedin:
            logger.error("Draft %d is not a LinkedIn draft", draft_id)
            return False

        # Use smartlead_lead_id as a "sent" marker for LinkedIn drafts
        draft.smartlead_lead_id = "manual"
        draft.updated_at = datetime.utcnow()

        prospect = session.get(Prospect, draft.prospect_id)
        if prospect:
            if prospect.status in (ProspectStatus.approved, ProspectStatus.drafted):
                prospect.status = ProspectStatus.sent
                prospect.updated_at = datetime.utcnow()

        action = "linkedin_connection_sent" if draft.sequence_step == 1 else "linkedin_message_sent"
        session.add(ActivityLog(
            prospect_id=draft.prospect_id,
            action=action,
            channel=Channel.linkedin,
            details=json.dumps({"draft_id": draft_id, "step": draft.sequence_step}),
        ))
        session.commit()

    logger.info("Marked LinkedIn draft %d as manually sent", draft_id)
    return True
