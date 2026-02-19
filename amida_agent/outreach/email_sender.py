"""Smartlead API integration for email sending.

Handles campaign creation, lead management, and email delivery
through the Smartlead API (https://server.smartlead.ai/api/v1).
"""

import json
import logging
import time
from datetime import datetime

import httpx

from amida_agent.config import settings
from amida_agent.database import get_session
from amida_agent.models import (
    ActivityLog,
    Channel,
    OutreachDraft,
    PEFirm,
    Prospect,
    ProspectStatus,
)

logger = logging.getLogger(__name__)

SMARTLEAD_BASE = "https://server.smartlead.ai/api/v1"

# Minimum delay between Smartlead API calls (seconds) to stay under 10 req/2s
_API_DELAY = 0.5


def _smartlead_request(method: str, path: str, **kwargs) -> dict:
    """Make a Smartlead API request with API key injection and retry on 429."""
    url = f"{SMARTLEAD_BASE}{path}"
    params = kwargs.pop("params", {})
    params["api_key"] = settings.smartlead_api_key

    max_retries = 3
    for attempt in range(max_retries):
        time.sleep(_API_DELAY)
        resp = httpx.request(method, url, params=params, timeout=30.0, **kwargs)

        if resp.status_code == 429:
            wait = 2 ** attempt
            logger.warning("Smartlead 429 rate limit, retrying in %ds", wait)
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp.json()

    raise RuntimeError(f"Smartlead API rate limited after {max_retries} retries: {path}")


def create_campaign(name: str) -> str:
    """Create a new Smartlead campaign. Returns campaign_id."""
    payload = {"name": name}
    if settings.smartlead_sending_account:
        payload["sending_account_id"] = settings.smartlead_sending_account

    data = _smartlead_request("POST", "/campaigns/create", json=payload)
    campaign_id = str(data.get("id", ""))
    logger.info("Created Smartlead campaign '%s' → %s", name, campaign_id)
    return campaign_id


def add_lead_to_campaign(campaign_id: str, prospect: Prospect, company_name: str = "") -> str:
    """Add a prospect as a lead to a Smartlead campaign. Returns lead_id."""
    lead_list = [
        {
            "email": prospect.email,
            "first_name": prospect.first_name,
            "last_name": prospect.last_name,
            "company_name": company_name,
        }
    ]
    data = _smartlead_request(
        "POST",
        f"/campaigns/{campaign_id}/leads",
        json={"lead_list": lead_list},
    )
    # Smartlead returns the upload status; extract lead ID
    lead_id = ""
    if isinstance(data, dict):
        upload_list = data.get("upload_list", [])
        if upload_list:
            lead_id = str(upload_list[0].get("id", ""))
    logger.info("Added lead %s to campaign %s → lead_id=%s", prospect.email, campaign_id, lead_id)
    return lead_id


def add_sequence_step(
    campaign_id: str,
    step: int,
    subject: str,
    body: str,
    delay_days: int = 0,
) -> None:
    """Add or update a sequence step in a Smartlead campaign."""
    _smartlead_request(
        "POST",
        f"/campaigns/{campaign_id}/sequences",
        json={
            "sequences": [
                {
                    "seq_number": step,
                    "subject": subject,
                    "email_body": body,
                    "seq_delay_details": {"delay_in_days": delay_days},
                }
            ],
        },
    )
    logger.info("Added sequence step %d to campaign %s (delay=%dd)", step, campaign_id, delay_days)


def send_approved_draft(draft_id: int) -> None:
    """Main entry point: send an approved draft via Smartlead.

    1. Load draft + prospect from DB
    2. Get or create Smartlead campaign
    3. Add sequence step (subject + body)
    4. Add lead to campaign
    5. Store Smartlead IDs on the draft
    6. Update prospect status: approved → sent
    7. Log to ActivityLog
    """
    if not settings.smartlead_api_key:
        logger.warning("SMARTLEAD_API_KEY not set — skipping send for draft %d", draft_id)
        return

    with get_session() as session:
        draft = session.get(OutreachDraft, draft_id)
        if not draft:
            logger.error("Draft %d not found", draft_id)
            return

        if draft.channel != Channel.email:
            logger.info("Draft %d is %s channel — skipping Smartlead send", draft_id, draft.channel)
            return

        prospect = session.get(Prospect, draft.prospect_id)
        if not prospect:
            logger.error("Prospect %d not found for draft %d", draft.prospect_id, draft_id)
            return

        if not prospect.email:
            logger.error("Prospect %d has no email — cannot send draft %d", prospect.id, draft_id)
            return

        # Use edited content if available
        subject = draft.subject
        body = draft.edited_body or draft.body

        # Create campaign per prospect for personalized sequences
        campaign_name = f"Amida – {prospect.full_name}"
        if draft.smartlead_campaign_id:
            campaign_id = draft.smartlead_campaign_id
        else:
            campaign_id = create_campaign(campaign_name)

        # Configure the sequence step
        step_delays = settings.step_delays
        delay = step_delays[draft.sequence_step - 2] if draft.sequence_step > 1 and len(step_delays) >= draft.sequence_step - 1 else 0
        add_sequence_step(campaign_id, draft.sequence_step, subject, body, delay_days=delay)

        # Look up company name from PE firm
        company_name = ""
        if prospect.pe_firm_id:
            firm = session.get(PEFirm, prospect.pe_firm_id)
            if firm:
                company_name = firm.name

        # Add lead
        if draft.smartlead_lead_id:
            lead_id = draft.smartlead_lead_id
        else:
            lead_id = add_lead_to_campaign(campaign_id, prospect, company_name=company_name)

        # Update draft with Smartlead IDs
        draft.smartlead_campaign_id = campaign_id
        draft.smartlead_lead_id = lead_id
        draft.updated_at = datetime.utcnow()

        # Update prospect status
        if prospect.status == ProspectStatus.approved:
            prospect.status = ProspectStatus.sent
            prospect.updated_at = datetime.utcnow()

        session.add(ActivityLog(
            prospect_id=prospect.id,
            action="email_sent",
            channel=Channel.email,
            details=json.dumps({
                "step": draft.sequence_step,
                "campaign_id": campaign_id,
                "lead_id": lead_id,
                "subject": subject,
            }),
        ))
        session.commit()

    logger.info(
        "Sent draft %d via Smartlead (campaign=%s, lead=%s, step=%d)",
        draft_id, campaign_id, lead_id, draft.sequence_step,
    )

    # macOS notification
    from amida_agent.notifications.notifier import notify
    notify("Email Sent", f"{prospect.full_name} — step {draft.sequence_step} sent via Smartlead")


def fetch_lead_status(campaign_id: str, lead_id: str) -> dict:
    """Get delivery/open/reply status for a lead from Smartlead."""
    if not settings.smartlead_api_key:
        return {}
    data = _smartlead_request("GET", f"/campaigns/{campaign_id}/leads/{lead_id}/status")
    return data


def fetch_campaign_stats(campaign_id: str) -> dict:
    """Get campaign-level metrics from Smartlead."""
    if not settings.smartlead_api_key:
        return {}
    data = _smartlead_request("GET", f"/campaigns/{campaign_id}/statistics")
    return data


