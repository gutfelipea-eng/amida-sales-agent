"""Shared Apify actor runner with 429 backoff."""

import asyncio
import logging

import httpx

from amida_agent.config import settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
_MAX_POLL_SECONDS = 300
_POLL_INTERVAL = 5
_MAX_RETRIES = 3


async def run_actor(actor_id: str, run_input: dict) -> list[dict]:
    """Start an Apify actor run, poll until done, return dataset items.

    Handles 429 rate-limit responses with exponential backoff.
    Returns empty list on failure.
    """
    if not settings.apify_api_key:
        logger.error("APIFY_API_KEY not set")
        return []

    headers = {"Authorization": f"Bearer {settings.apify_api_key}"}

    # --- Start run ---
    run_id = await _start_run(actor_id, run_input, headers)
    if not run_id:
        return []

    # --- Poll until finished ---
    status = await _poll_run(run_id, headers)
    if status != "SUCCEEDED":
        logger.error("Apify run %s finished with status: %s", run_id, status)
        return []

    # --- Fetch dataset ---
    return await _fetch_dataset(run_id, headers)


async def _start_run(
    actor_id: str, run_input: dict, headers: dict
) -> str | None:
    """POST to start an actor run. Returns run ID or None."""
    url = f"{APIFY_BASE}/acts/{actor_id}/runs"

    for attempt in range(_MAX_RETRIES):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=run_input, headers=headers)

        if resp.status_code == 201:
            data = resp.json().get("data", {})
            run_id = data.get("id")
            logger.info("Started Apify run %s for actor %s", run_id, actor_id)
            return run_id

        if resp.status_code == 429:
            wait = 2 ** (attempt + 1)
            logger.warning("Apify 429 — retrying in %ds (attempt %d)", wait, attempt + 1)
            await asyncio.sleep(wait)
            continue

        logger.error("Apify start error %d: %s", resp.status_code, resp.text[:200])
        return None

    logger.error("Apify start failed after %d retries", _MAX_RETRIES)
    return None


async def _poll_run(run_id: str, headers: dict) -> str:
    """Poll run status until terminal state. Returns status string."""
    url = f"{APIFY_BASE}/actor-runs/{run_id}"
    elapsed = 0

    while elapsed < _MAX_POLL_SECONDS:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 200:
            status = resp.json().get("data", {}).get("status", "UNKNOWN")
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                return status
        else:
            logger.warning("Apify poll error %d", resp.status_code)

        await asyncio.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL

    logger.error("Apify run %s timed out after %ds", run_id, _MAX_POLL_SECONDS)
    return "TIMED-OUT"


async def _fetch_dataset(run_id: str, headers: dict) -> list[dict]:
    """Fetch dataset items from a completed run."""
    url = f"{APIFY_BASE}/actor-runs/{run_id}/dataset/items"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code != 200:
        logger.error("Apify dataset error %d: %s", resp.status_code, resp.text[:200])
        return []

    items = resp.json()
    logger.info("Fetched %d items from Apify run %s", len(items), run_id)
    return items if isinstance(items, list) else []
