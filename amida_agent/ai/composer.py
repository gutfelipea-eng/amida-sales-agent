"""AI-powered outreach message composer using Claude."""

import logging
import re

from amida_agent.ai.client import generate
from amida_agent.ai.prompts import (
    EMAIL_BREAKUP,
    EMAIL_CASE_STUDY,
    EMAIL_FIRST_TOUCH,
    EMAIL_FOLLOW_UP,
    LINKEDIN_CONNECTION,
    LINKEDIN_FIRST_MESSAGE,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def _parse_email_response(text: str) -> tuple[str, str]:
    """Parse SUBJECT: / BODY: format from AI response."""
    subject = ""
    body = text

    # Try to extract subject line
    match = re.search(r"SUBJECT:\s*(.+?)(?:\n|$)", text)
    if match:
        subject = match.group(1).strip()

    # Extract body after BODY: marker
    match = re.search(r"BODY:\s*\n(.*)", text, re.DOTALL)
    if match:
        body = match.group(1).strip()

    return subject, body


def compose_email(
    dossier: str,
    sequence_step: int = 1,
    previous_email: str = "",
) -> tuple[str, str]:
    """Compose a personalized email using Claude.

    Returns (subject, body).
    """
    if sequence_step == 1:
        prompt = EMAIL_FIRST_TOUCH.format(dossier=dossier)
    elif sequence_step == 2:
        prompt = EMAIL_FOLLOW_UP.format(
            dossier=dossier,
            previous_email=previous_email,
            step_number=sequence_step,
        )
    elif sequence_step == 3:
        prompt = EMAIL_CASE_STUDY.format(
            dossier=dossier,
            step_number=sequence_step,
        )
    else:
        prompt = EMAIL_BREAKUP.format(
            dossier=dossier,
            step_number=sequence_step,
        )

    response = generate(
        system=SYSTEM_PROMPT,
        prompt=prompt,
        temperature=0.7,
    )

    subject, body = _parse_email_response(response)
    logger.info("Composed email step %d: subject='%s' (%d chars)", sequence_step, subject, len(body))
    return subject, body


def compose_linkedin_connection(dossier: str) -> str:
    """Compose a LinkedIn connection request message."""
    prompt = LINKEDIN_CONNECTION.format(dossier=dossier)
    response = generate(
        system=SYSTEM_PROMPT,
        prompt=prompt,
        max_tokens=256,
        temperature=0.7,
    )
    # Trim to 280 chars (LinkedIn limit)
    text = response.strip()
    if len(text) > 280:
        text = text[:277] + "..."
    return text


def compose_linkedin_message(dossier: str) -> str:
    """Compose a LinkedIn DM (post-connection)."""
    prompt = LINKEDIN_FIRST_MESSAGE.format(dossier=dossier)
    response = generate(
        system=SYSTEM_PROMPT,
        prompt=prompt,
        max_tokens=256,
        temperature=0.7,
    )
    return response.strip()


def compose_full_sequence(dossier: str) -> list[tuple[int, str, str]]:
    """Generate all 4 email sequence steps.

    Returns list of (step, subject, body).
    """
    results = []
    previous = ""

    for step in range(1, 5):
        subject, body = compose_email(dossier, sequence_step=step, previous_email=previous)
        results.append((step, subject, body))
        previous = f"Subject: {subject}\n\n{body}"

    return results
