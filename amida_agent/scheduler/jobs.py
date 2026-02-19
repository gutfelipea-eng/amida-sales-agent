"""APScheduler background jobs for scout automation.

Schedule:
  - Full scan (all 3 scouts):   Mon + Thu at 08:00
  - People search only:         Daily at 06:00
  - News monitor:               Every 12 hours
"""

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from amida_agent.config import settings

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_async(coro):
    """Run an async coroutine from a sync APScheduler job."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()


def _job_full_scan():
    """Scheduled job: run all scouts."""
    from amida_agent.scout.pipeline import run_full_scan
    logger.info("Scheduled job: full_scan starting")
    _run_async(run_full_scan())


def _job_people_search():
    """Scheduled job: people search only."""
    from amida_agent.scout.people_search import search_all_firms
    logger.info("Scheduled job: people_search starting")
    _run_async(search_all_firms())


def _job_news_monitor():
    """Scheduled job: news monitor only."""
    from amida_agent.scout.news_monitor import scan_all_firms
    logger.info("Scheduled job: news_monitor starting")
    _run_async(scan_all_firms())


def _job_sequence_check():
    """Scheduled job: check and progress email sequences."""
    from amida_agent.outreach.sequence_manager import check_sequence_progression
    logger.info("Scheduled job: sequence_check starting")
    result = check_sequence_progression()
    logger.info("Scheduled job: sequence_check done — %s", result)


def _job_sync_smartlead():
    """Scheduled job: sync reply/open status from Smartlead."""
    from amida_agent.outreach.sequence_manager import sync_smartlead_statuses
    logger.info("Scheduled job: sync_smartlead starting")
    result = sync_smartlead_statuses()
    logger.info("Scheduled job: sync_smartlead done — %s", result)


def start_scheduler() -> BackgroundScheduler:
    """Start the background scheduler with all scout jobs."""
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.warning("Scheduler already running")
        return _scheduler

    _scheduler = BackgroundScheduler(
        job_defaults={"coalesce": True, "max_instances": 1},
    )

    # Full scan: Mon + Thu at 08:00
    _scheduler.add_job(
        _job_full_scan,
        trigger=CronTrigger(day_of_week="mon,thu", hour=8, minute=0),
        id="full_scan",
        name="Full scout scan (Mon+Thu 08:00)",
        replace_existing=True,
    )

    # People search: daily at 06:00
    _scheduler.add_job(
        _job_people_search,
        trigger=CronTrigger(hour=6, minute=0),
        id="people_search",
        name="People search (daily 06:00)",
        replace_existing=True,
    )

    # News monitor: every N hours (configurable)
    _scheduler.add_job(
        _job_news_monitor,
        trigger=IntervalTrigger(hours=settings.scout_news_interval_hours),
        id="news_monitor",
        name=f"News monitor (every {settings.scout_news_interval_hours}h)",
        replace_existing=True,
    )

    # Sequence progression: daily at 10:00
    _scheduler.add_job(
        _job_sequence_check,
        trigger=CronTrigger(hour=10, minute=0),
        id="sequence_check",
        name="Sequence progression (daily 10:00)",
        replace_existing=True,
    )

    # Smartlead status sync: every 6 hours
    _scheduler.add_job(
        _job_sync_smartlead,
        trigger=IntervalTrigger(hours=6),
        id="sync_smartlead",
        name="Smartlead status sync (every 6h)",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))
    for job in _scheduler.get_jobs():
        logger.info("  Job: %s — next run: %s", job.name, job.next_run_time)

    return _scheduler


def stop_scheduler() -> None:
    """Stop the background scheduler gracefully."""
    global _scheduler

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None
