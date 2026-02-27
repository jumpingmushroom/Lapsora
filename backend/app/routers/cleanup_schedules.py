"""Cleanup schedule CRUD endpoints."""

import logging

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CleanupSchedule, Profile
from app.schemas import (
    CleanupScheduleCreate,
    CleanupScheduleRead,
    CleanupScheduleUpdate,
)
from app.services.scheduler import (
    add_cleanup_schedule_job,
    remove_cleanup_schedule_job,
    scheduler,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cleanup-schedules", tags=["cleanup-schedules"])


def _validate_cron(expr: str) -> None:
    try:
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError("Cron expression must have 5 fields")
        CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
    except Exception as e:
        raise HTTPException(422, f"Invalid cron expression: {e}") from e


def _schedule_to_read(schedule: CleanupSchedule) -> dict:
    data = CleanupScheduleRead.model_validate(schedule).model_dump()
    job = scheduler.get_job(f"cleanup_schedule_{schedule.id}")
    if job and job.next_run_time:
        data["next_run"] = job.next_run_time.isoformat()
    else:
        data["next_run"] = None
    return data


@router.get("/", response_model=list[CleanupScheduleRead])
def list_cleanup_schedules(
    profile_id: int | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(CleanupSchedule).order_by(CleanupSchedule.created_at.desc())
    if profile_id is not None:
        stmt = stmt.where(CleanupSchedule.profile_id == profile_id)
    schedules = db.execute(stmt).scalars().all()
    return [_schedule_to_read(s) for s in schedules]


@router.post("/", response_model=CleanupScheduleRead, status_code=201)
def create_cleanup_schedule(
    body: CleanupScheduleCreate,
    db: Session = Depends(get_db),
):
    profile = db.get(Profile, body.profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")

    _validate_cron(body.cron_expression)

    schedule = CleanupSchedule(
        profile_id=body.profile_id,
        name=body.name,
        capture_retention_days=body.capture_retention_days,
        timelapse_retention_days=body.timelapse_retention_days,
        cron_expression=body.cron_expression,
        enabled=body.enabled,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    if schedule.enabled:
        add_cleanup_schedule_job(schedule)

    return _schedule_to_read(schedule)


@router.put("/{schedule_id}", response_model=CleanupScheduleRead)
def update_cleanup_schedule(
    schedule_id: int,
    body: CleanupScheduleUpdate,
    db: Session = Depends(get_db),
):
    schedule = db.get(CleanupSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    updates = body.model_dump(exclude_unset=True)

    if "cron_expression" in updates:
        _validate_cron(updates["cron_expression"])

    for key, value in updates.items():
        setattr(schedule, key, value)

    db.commit()
    db.refresh(schedule)

    remove_cleanup_schedule_job(schedule.id)
    if schedule.enabled:
        add_cleanup_schedule_job(schedule)

    return _schedule_to_read(schedule)


@router.delete("/{schedule_id}", status_code=204)
def delete_cleanup_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
):
    schedule = db.get(CleanupSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    remove_cleanup_schedule_job(schedule.id)
    db.delete(schedule)
    db.commit()


@router.post("/{schedule_id}/trigger", status_code=202)
async def trigger_cleanup_schedule(
    schedule_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    schedule = db.get(CleanupSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    from app.services.retention import run_profile_cleanup

    background_tasks.add_task(
        run_profile_cleanup,
        profile_id=schedule.profile_id,
        capture_retention_days=schedule.capture_retention_days,
        timelapse_retention_days=schedule.timelapse_retention_days,
    )
    return {"status": "running", "message": "Cleanup triggered"}
