"""macOS native notifications via osascript."""

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


def notify(title: str, message: str, sound: str = "Ping") -> bool:
    """Send a macOS notification. Returns True if successful."""
    if sys.platform != "darwin":
        logger.debug("Notifications only supported on macOS")
        return False

    script = (
        f'display notification "{_escape(message)}" '
        f'with title "{_escape(title)}" '
        f'sound name "{sound}"'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("Notification failed: %s", e)
        return False


def notify_new_lead(name: str, firm: str, score: float) -> bool:
    """Notify when a new high-score lead is found."""
    return notify(
        "New Lead Found",
        f"{name} at {firm} — {score:.0%} relevance",
    )


def notify_needs_approval(count: int) -> bool:
    """Notify when drafts are waiting for approval."""
    s = "s" if count != 1 else ""
    return notify(
        "Drafts Need Review",
        f"{count} outreach draft{s} awaiting your approval",
        sound="Submarine",
    )


def notify_reply(name: str) -> bool:
    """Notify when a prospect replies."""
    return notify(
        "Prospect Replied!",
        f"{name} replied to your outreach",
        sound="Hero",
    )


def notify_meeting(name: str) -> bool:
    """Notify when a meeting is booked."""
    return notify(
        "Meeting Booked!",
        f"Meeting booked with {name}",
        sound="Glass",
    )


def _escape(text: str) -> str:
    """Escape double quotes and backslashes for AppleScript."""
    return text.replace("\\", "\\\\").replace('"', '\\"')
