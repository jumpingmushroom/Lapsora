"""Timelapse schedule CRUD endpoints."""

import logging

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, TimelapseSchedule
from app.schemas import (
    TimelapseScheduleCreate,
    TimelapseScheduleRead,
    TimelapseScheduleUpdate,
)
from app.services.scheduler import (
    add_timelapse_schedule_job,
    remove_timelapse_schedule_job,
    scheduler,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/timelapse-schedules", tags=["timelapse-schedules"])

PRESET_CRONS = {
    "daily": "5 0 * * *",
    "weekly": "30 0 * * 0",
    "monthly": "0 1 1 * *",
    "yearly": "0 2 1 1 *",
}

PRESET_LOOKBACK = {"daily": 24, "weekly": 168, "monthly": 730, "yearly": 8760}


def _validate_cron(expr: str) -> None:
    """Validate a cron expression by trying to build a trigger."""
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


def _schedule_to_read(schedule: TimelapseSchedule) -> dict:
    """Convert a schedule to a read dict with next_run."""
    data = TimelapseScheduleRead.model_validate(schedule).model_dump()
    job = scheduler.get_job(f"timelapse_schedule_{schedule.id}")
    if job and job.next_run_time:
        data["next_run"] = job.next_run_time.isoformat()
    else:
        data["next_run"] = None
    return data


@router.get("/", response_model=list[TimelapseScheduleRead])
def list_schedules(
    profile_id: int | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(TimelapseSchedule).order_by(TimelapseSchedule.created_at.desc())
    if profile_id is not None:
        stmt = stmt.where(TimelapseSchedule.profile_id == profile_id)
    schedules = db.execute(stmt).scalars().all()
    return [_schedule_to_read(s) for s in schedules]


@router.post("/", response_model=TimelapseScheduleRead, status_code=201)
def create_schedule(
    body: TimelapseScheduleCreate,
    db: Session = Depends(get_db),
):
    # Validate profile exists
    profile = db.get(Profile, body.profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")

    # Resolve cron expression
    cron = body.cron_expression
    if body.preset:
        if body.preset not in PRESET_CRONS:
            raise HTTPException(422, f"Unknown preset: {body.preset}")
        cron = PRESET_CRONS[body.preset]
    if not cron:
        raise HTTPException(422, "cron_expression is required when preset is not set")

    _validate_cron(cron)

    lookback = body.lookback_hours
    if body.preset and lookback is None:
        lookback = PRESET_LOOKBACK.get(body.preset)

    schedule = TimelapseSchedule(
        profile_id=body.profile_id,
        name=body.name,
        preset=body.preset,
        cron_expression=cron,
        fps=body.fps,
        format=body.format,
        deflicker=body.deflicker,
        lookback_hours=lookback,
        timestamp_overlay=body.timestamp_overlay,
        weather_overlay=body.weather_overlay,
        weather_position=body.weather_position,
        weather_font_size=body.weather_font_size,
        weather_unit=body.weather_unit,
        heatmap_overlay=body.heatmap_overlay,
        heatmap_mode=body.heatmap_mode,
        heatmap_opacity=body.heatmap_opacity,
        heatmap_colormap=body.heatmap_colormap,
        heatmap_threshold=body.heatmap_threshold,
        enabled=body.enabled,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    if schedule.enabled:
        add_timelapse_schedule_job(schedule)

    return _schedule_to_read(schedule)


@router.put("/{schedule_id}", response_model=TimelapseScheduleRead)
def update_schedule(
    schedule_id: int,
    body: TimelapseScheduleUpdate,
    db: Session = Depends(get_db),
):
    schedule = db.get(TimelapseSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    updates = body.model_dump(exclude_unset=True)

    # If preset is being changed, update cron_expression and lookback
    if "preset" in updates and updates["preset"]:
        if updates["preset"] not in PRESET_CRONS:
            raise HTTPException(422, f"Unknown preset: {updates['preset']}")
        updates["cron_expression"] = PRESET_CRONS[updates["preset"]]
        if "lookback_hours" not in updates:
            updates["lookback_hours"] = PRESET_LOOKBACK.get(updates["preset"])

    if "cron_expression" in updates:
        _validate_cron(updates["cron_expression"])

    for key, value in updates.items():
        setattr(schedule, key, value)

    db.commit()
    db.refresh(schedule)

    # Reschedule the job
    remove_timelapse_schedule_job(schedule.id)
    if schedule.enabled:
        add_timelapse_schedule_job(schedule)

    return _schedule_to_read(schedule)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
):
    schedule = db.get(TimelapseSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    remove_timelapse_schedule_job(schedule.id)
    db.delete(schedule)
    db.commit()


@router.post("/{schedule_id}/trigger", status_code=202)
async def trigger_schedule(
    schedule_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    schedule = db.get(TimelapseSchedule, schedule_id)
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    from datetime import datetime, timedelta

    from app.services.timelapse import generate_timelapse, get_period_range

    if schedule.lookback_hours is not None:
        end = datetime.now()
        start = end - timedelta(hours=schedule.lookback_hours)
        period = schedule.preset or "custom"
    else:
        period = schedule.preset or "daily"
        start, end = get_period_range(period)

    background_tasks.add_task(
        generate_timelapse,
        profile_id=schedule.profile_id,
        period_type=period,
        period_start=start,
        period_end=end,
        fps=schedule.fps,
        format=schedule.format,
        deflicker=schedule.deflicker,
        timestamp_overlay=schedule.timestamp_overlay,
        weather_overlay=schedule.weather_overlay,
        weather_position=schedule.weather_position,
        weather_font_size=schedule.weather_font_size,
        weather_unit=schedule.weather_unit,
        heatmap_overlay=schedule.heatmap_overlay,
        heatmap_mode=schedule.heatmap_mode,
        heatmap_opacity=schedule.heatmap_opacity,
        heatmap_colormap=schedule.heatmap_colormap,
        heatmap_threshold=schedule.heatmap_threshold,
    )
    return {"status": "generating", "message": "Timelapse generation triggered"}
