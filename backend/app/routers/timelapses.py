"""Timelapse management endpoints."""

import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Timelapse
from app.schemas import BulkDeleteRequest, TimelapseGenerate, TimelapseRead
from app.services.timelapse import generate_timelapse

router = APIRouter(prefix="/api", tags=["timelapses"])

MEDIA_TYPES = {
    "mp4": "video/mp4",
    "webm": "video/webm",
    "gif": "image/gif",
}


@router.get("/timelapses", response_model=list[TimelapseRead])
def list_timelapses(
    profile_id: int | None = None,
    period_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Timelapse).order_by(Timelapse.created_at.desc())
    if profile_id is not None:
        stmt = stmt.where(Timelapse.profile_id == profile_id)
    if period_type is not None:
        stmt = stmt.where(Timelapse.period_type == period_type)
    stmt = stmt.offset(offset).limit(limit)
    return db.execute(stmt).scalars().all()


@router.post(
    "/profiles/{profile_id}/timelapses/generate",
    status_code=202,
)
async def generate(
    profile_id: int,
    body: TimelapseGenerate,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(
        generate_timelapse,
        profile_id=profile_id,
        period_type="custom",
        period_start=body.period_start,
        period_end=body.period_end,
        fps=body.fps,
        format=body.format,
        timestamp_overlay=body.timestamp_overlay,
        weather_overlay=body.weather_overlay,
        weather_position=body.weather_position,
        weather_font_size=body.weather_font_size,
        weather_unit=body.weather_unit,
        deflicker=body.deflicker,
        heatmap_overlay=body.heatmap_overlay,
        heatmap_mode=body.heatmap_mode,
        heatmap_opacity=body.heatmap_opacity,
        heatmap_colormap=body.heatmap_colormap,
        heatmap_threshold=body.heatmap_threshold,
    )
    return {"status": "generating", "message": "Timelapse generation started"}


@router.get("/timelapses/{timelapse_id}", response_model=TimelapseRead)
def get_timelapse(timelapse_id: int, db: Session = Depends(get_db)):
    tl = db.get(Timelapse, timelapse_id)
    if not tl:
        raise HTTPException(404, "Timelapse not found")
    return tl


@router.get("/timelapses/{timelapse_id}/video")
def get_timelapse_video(timelapse_id: int, db: Session = Depends(get_db)):
    tl = db.get(Timelapse, timelapse_id)
    if not tl:
        raise HTTPException(404, "Timelapse not found")
    if not os.path.exists(tl.file_path):
        raise HTTPException(404, "Timelapse file not found on disk")
    media_type = MEDIA_TYPES.get(tl.format, "application/octet-stream")
    return FileResponse(
        tl.file_path,
        media_type=media_type,
        filename=os.path.basename(tl.file_path),
    )


@router.delete("/timelapses/bulk", status_code=204)
def bulk_delete_timelapses(body: BulkDeleteRequest, db: Session = Depends(get_db)):
    tls = db.query(Timelapse).filter(Timelapse.id.in_(body.ids)).all()
    for tl in tls:
        if os.path.exists(tl.file_path):
            os.unlink(tl.file_path)
        db.delete(tl)
    db.commit()


@router.delete("/timelapses/{timelapse_id}", status_code=204)
def delete_timelapse(timelapse_id: int, db: Session = Depends(get_db)):
    tl = db.get(Timelapse, timelapse_id)
    if not tl:
        raise HTTPException(404, "Timelapse not found")
    if os.path.exists(tl.file_path):
        os.unlink(tl.file_path)
    db.delete(tl)
    db.commit()
