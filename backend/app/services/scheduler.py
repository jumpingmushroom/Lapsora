"""APScheduler-based capture scheduling."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.models import Profile

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def init_scheduler() -> None:
    """Configure and start the scheduler."""
    scheduler.start()
    logger.info("Capture scheduler started")


def add_capture_job(profile: Profile) -> None:
    """Add an interval job for capturing frames."""
    from app.services.capture import capture_frame

    job_id = f"capture_{profile.id}"
    scheduler.add_job(
        capture_frame,
        "interval",
        seconds=profile.interval_seconds,
        id=job_id,
        replace_existing=True,
        args=[profile.id],
    )
    logger.info("Added capture job %s (every %ds)", job_id, profile.interval_seconds)


def remove_capture_job(profile_id: int) -> None:
    """Remove a capture job. Silently ignores missing jobs."""
    job_id = f"capture_{profile_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info("Removed capture job %s", job_id)
    except Exception:
        logger.debug("Job %s not found, nothing to remove", job_id)


def reschedule_capture_job(profile: Profile) -> None:
    """Remove and re-add a capture job with updated settings."""
    remove_capture_job(profile.id)
    add_capture_job(profile)


def restore_jobs(db: Session) -> None:
    """Restore capture jobs for all enabled profiles."""
    profiles = db.query(Profile).filter(Profile.enabled.is_(True)).all()
    for profile in profiles:
        try:
            add_capture_job(profile)
        except Exception:
            logger.exception("Failed to restore job for profile %d", profile.id)
    logger.info("Restored %d capture jobs", len(profiles))


def add_scheduled_timelapse_jobs() -> None:
    """Add periodic timelapse generation jobs."""
    from app.services.timelapse import generate_timelapse, get_period_range

    async def _run_scheduled(period_type: str):
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            profiles = db.query(Profile).filter(Profile.enabled.is_(True)).all()
            for profile in profiles:
                try:
                    start, end = get_period_range(period_type)
                    await generate_timelapse(
                        profile_id=profile.id,
                        period_type=period_type,
                        period_start=start,
                        period_end=end,
                    )
                except Exception:
                    logger.exception(
                        "Scheduled %s timelapse failed for profile %d",
                        period_type, profile.id,
                    )
        finally:
            db.close()

    # Daily at 00:05
    scheduler.add_job(
        _run_scheduled, "cron", hour=0, minute=5,
        id="timelapse_daily", replace_existing=True, args=["daily"],
    )
    # Weekly on Sunday at 00:30
    scheduler.add_job(
        _run_scheduled, "cron", day_of_week="sun", hour=0, minute=30,
        id="timelapse_weekly", replace_existing=True, args=["weekly"],
    )
    # Monthly on 1st at 01:00
    scheduler.add_job(
        _run_scheduled, "cron", day=1, hour=1, minute=0,
        id="timelapse_monthly", replace_existing=True, args=["monthly"],
    )
    # Yearly on Jan 1 at 02:00
    scheduler.add_job(
        _run_scheduled, "cron", month=1, day=1, hour=2, minute=0,
        id="timelapse_yearly", replace_existing=True, args=["yearly"],
    )
    logger.info("Scheduled timelapse generation jobs added")


def add_retention_job() -> None:
    """Add daily retention cleanup job at 03:00."""
    from app.services.retention import run_retention_cleanup

    scheduler.add_job(
        run_retention_cleanup, "cron", hour=3, minute=0,
        id="retention_cleanup", replace_existing=True,
    )
    logger.info("Retention cleanup job scheduled at 03:00 daily")
