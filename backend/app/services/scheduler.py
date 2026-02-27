"""APScheduler-based capture scheduling."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.models import CleanupSchedule, Profile, TimelapseSchedule

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

    # Restore timelapse schedule jobs
    schedules = db.query(TimelapseSchedule).filter(TimelapseSchedule.enabled.is_(True)).all()
    for schedule in schedules:
        try:
            add_timelapse_schedule_job(schedule)
        except Exception:
            logger.exception("Failed to restore timelapse schedule job %d", schedule.id)
    logger.info("Restored %d timelapse schedule jobs", len(schedules))

    # Restore cleanup schedule jobs
    cleanup_schedules = db.query(CleanupSchedule).filter(CleanupSchedule.enabled.is_(True)).all()
    for cs in cleanup_schedules:
        try:
            add_cleanup_schedule_job(cs)
        except Exception:
            logger.exception("Failed to restore cleanup schedule job %d", cs.id)
    logger.info("Restored %d cleanup schedule jobs", len(cleanup_schedules))


def add_timelapse_schedule_job(schedule: TimelapseSchedule) -> None:
    """Register an APScheduler cron job for a timelapse schedule."""
    from app.services.timelapse import generate_timelapse, get_period_range

    async def _run_schedule(schedule_id: int, profile_id: int, preset: str | None, fps: int, fmt: str):
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            # Re-check the schedule is still enabled
            sched = db.get(TimelapseSchedule, schedule_id)
            if not sched or not sched.enabled:
                return
            period = preset or "daily"
            start, end = get_period_range(period)
            await generate_timelapse(
                profile_id=profile_id,
                period_type=period,
                period_start=start,
                period_end=end,
                fps=fps,
                format=fmt,
            )
        except Exception:
            logger.exception(
                "Scheduled timelapse failed for schedule %d (profile %d)",
                schedule_id, profile_id,
            )
        finally:
            db.close()

    parts = schedule.cron_expression.strip().split()
    job_id = f"timelapse_schedule_{schedule.id}"
    scheduler.add_job(
        _run_schedule,
        "cron",
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
        id=job_id,
        replace_existing=True,
        args=[schedule.id, schedule.profile_id, schedule.preset, schedule.fps, schedule.format],
    )
    logger.info("Added timelapse schedule job %s (cron: %s)", job_id, schedule.cron_expression)


def remove_timelapse_schedule_job(schedule_id: int) -> None:
    """Remove an APScheduler job for a timelapse schedule."""
    job_id = f"timelapse_schedule_{schedule_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info("Removed timelapse schedule job %s", job_id)
    except Exception:
        logger.debug("Job %s not found, nothing to remove", job_id)


def add_cleanup_schedule_job(schedule: CleanupSchedule) -> None:
    """Register an APScheduler cron job for a cleanup schedule."""
    from app.services.retention import run_profile_cleanup

    async def _run_cleanup(schedule_id: int, profile_id: int, capture_days: int, timelapse_days: int):
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            sched = db.get(CleanupSchedule, schedule_id)
            if not sched or not sched.enabled:
                return
            await run_profile_cleanup(
                profile_id=profile_id,
                capture_retention_days=capture_days,
                timelapse_retention_days=timelapse_days,
            )
        except Exception:
            logger.exception(
                "Scheduled cleanup failed for schedule %d (profile %d)",
                schedule_id, profile_id,
            )
        finally:
            db.close()

    parts = schedule.cron_expression.strip().split()
    job_id = f"cleanup_schedule_{schedule.id}"
    scheduler.add_job(
        _run_cleanup,
        "cron",
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
        id=job_id,
        replace_existing=True,
        args=[schedule.id, schedule.profile_id, schedule.capture_retention_days, schedule.timelapse_retention_days],
    )
    logger.info("Added cleanup schedule job %s (cron: %s)", job_id, schedule.cron_expression)


def remove_cleanup_schedule_job(schedule_id: int) -> None:
    """Remove an APScheduler job for a cleanup schedule."""
    job_id = f"cleanup_schedule_{schedule_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info("Removed cleanup schedule job %s", job_id)
    except Exception:
        logger.debug("Job %s not found, nothing to remove", job_id)


def add_capture_gap_job() -> None:
    """Add periodic capture gap check job (every 60 minutes)."""
    from app.services.capture_gap import check_capture_gaps

    scheduler.add_job(
        check_capture_gaps, "interval", seconds=3600,
        id="capture_gap_check", replace_existing=True,
    )
    logger.info("Capture gap check job scheduled every 3600s")


def remove_capture_gap_job() -> None:
    """Remove the capture gap check job."""
    try:
        scheduler.remove_job("capture_gap_check")
        logger.info("Removed capture gap check job")
    except Exception:
        logger.debug("Capture gap check job not found, nothing to remove")


def add_health_check_job(interval_seconds: int = 300) -> None:
    """Add periodic stream health check job."""
    from app.services.health import check_all_streams

    scheduler.add_job(
        check_all_streams, "interval", seconds=interval_seconds,
        id="health_check", replace_existing=True,
    )
    logger.info("Health check job scheduled every %ds", interval_seconds)


