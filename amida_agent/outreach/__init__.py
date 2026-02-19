"""Outreach automation: email sending, sequences, and LinkedIn queue."""

from amida_agent.outreach.email_sender import send_approved_draft
from amida_agent.outreach.linkedin_queue import (
    get_pending_linkedin_actions,
    mark_linkedin_sent,
    queue_connection_request,
    queue_linkedin_message,
)
from amida_agent.outreach.sequence_manager import (
    check_sequence_progression,
    get_sequence_status,
    handle_reply,
    sync_smartlead_statuses,
)

__all__ = [
    "send_approved_draft",
    "queue_connection_request",
    "queue_linkedin_message",
    "get_pending_linkedin_actions",
    "mark_linkedin_sent",
    "check_sequence_progression",
    "get_sequence_status",
    "handle_reply",
    "sync_smartlead_statuses",
]
