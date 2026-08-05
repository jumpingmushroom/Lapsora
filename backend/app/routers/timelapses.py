"""Timelapse management endpoints."""

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, Timelapse
from app.schemas import BulkDeleteRequest, TimelapseGenerate, TimelapseRead
from app.services.files import safe_remove
from app.services.generation_queue import enqueue_generation

router = APIRouter(prefix="/api", tags=["timelapses"])

MEDIA_TYPES = {
    "mp4": "video/mp4",
    "webm": "video/webm",
    "gif": "image/gif",
}


@router.get("/timelapses", response_model=list[TimelapseRead])
def list_timelapses(
    profile_id: int | None = None,
    stream_id: int | None = None,
    period_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Timelapse).order_by(Timelapse.created_at.desc())
    if profile_id is not None:
        stmt = stmt.where(Timelapse.profile_id == profile_id)
    elif stream_id is not None:
        # All timelapses for a stream in one query (one merged timeline) instead
        # of a per-profile fetch fan-out from the frontend.
        stmt = stmt.join(Profile, Timelapse.profile_id == Profile.id).where(
            Profile.stream_id == stream_id
        )
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
    db: Session = Depends(get_db),
):
    if not db.get(Profile, profile_id):
        raise HTTPException(404, "Profile not found")
    result = await enqueue_generation(
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
        weather_style=body.weather_style,
        ha_overlay=body.ha_overlay,
        ha_overlay_position=body.ha_overlay_position,
        deflicker=body.deflicker,
        heatmap_overlay=body.heatmap_overlay,
        heatmap_mode=body.heatmap_mode,
        heatmap_colormap=body.heatmap_colormap,
        heatmap_threshold=body.heatmap_threshold,
        logo_overlay=body.logo_overlay,
        logo_position=body.logo_position,
        logo_size=body.logo_size,
        logo_opacity=body.logo_opacity,
        motion_blur=body.motion_blur,
        codec=body.codec,
        output_width=body.output_width,
        output_height=body.output_height,
        quality_preset=body.quality_preset,
    )
    return {"status": "queued", "message": "Timelapse generation queued", **result}


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


@router.get("/timelapses/{timelapse_id}/thumbnail")
def get_timelapse_thumbnail(timelapse_id: int, db: Session = Depends(get_db)):
    tl = db.get(Timelapse, timelapse_id)
    if not tl:
        raise HTTPException(404, "Timelapse not found")
    if not tl.thumbnail_path or not os.path.exists(tl.thumbnail_path):
        raise HTTPException(404, "Thumbnail not available")
    return FileResponse(tl.thumbnail_path, media_type="image/jpeg")


@router.delete("/timelapses/bulk", status_code=204)
def bulk_delete_timelapses(body: BulkDeleteRequest, db: Session = Depends(get_db)):
    tls = db.query(Timelapse).filter(Timelapse.id.in_(body.ids)).all()
    # Commit row removal before unlinking so a failed commit can't leave the
    # media gone but the row (and its 404-ing endpoints) behind.
    paths = [(tl.file_path, tl.thumbnail_path) for tl in tls]
    for tl in tls:
        db.delete(tl)
    db.commit()
    for file_path, thumb_path in paths:
        safe_remove(file_path)
        safe_remove(thumb_path)


@router.delete("/timelapses/{timelapse_id}", status_code=204)
def delete_timelapse(timelapse_id: int, db: Session = Depends(get_db)):
    tl = db.get(Timelapse, timelapse_id)
    if not tl:
        raise HTTPException(404, "Timelapse not found")
    file_path, thumb_path = tl.file_path, tl.thumbnail_path
    db.delete(tl)
    db.commit()
    safe_remove(file_path)
    safe_remove(thumb_path)
