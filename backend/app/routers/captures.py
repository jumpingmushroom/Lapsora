"""Capture management endpoints."""

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Capture, Profile
from app.schemas import BulkDeleteRequest, CaptureRead
from app.services.files import safe_remove

router = APIRouter(prefix="/api", tags=["captures"])


@router.get("/captures", response_model=list[CaptureRead])
def list_captures_across_profiles(
    stream_id: int | None = None,
    profile_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Captures across one or more profiles with a single global ordering and
    pagination. The files page uses this so paging through "all profiles" walks
    one merged timeline; paginating each profile separately skipped rows."""
    q = db.query(Capture)
    if profile_id is not None:
        q = q.filter(Capture.profile_id == profile_id)
    elif stream_id is not None:
        q = q.join(Profile, Capture.profile_id == Profile.id).filter(
            Profile.stream_id == stream_id
        )
    return (
        q.order_by(Capture.captured_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/profiles/{profile_id}/captures", response_model=list[CaptureRead])
def list_captures(
    profile_id: int,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return (
        db.query(Capture)
        .filter(Capture.profile_id == profile_id)
        .order_by(Capture.captured_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/captures/{capture_id}/image")
def get_capture_image(capture_id: int, db: Session = Depends(get_db)):
    capture = db.get(Capture, capture_id)
    if not capture:
        raise HTTPException(404, "Capture not found")

    abs_path = os.path.join(settings.DATA_DIR, capture.file_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(404, "Capture file not found on disk")

    return FileResponse(abs_path, media_type="image/jpeg")


@router.delete("/captures/bulk", status_code=204)
def bulk_delete_captures(body: BulkDeleteRequest, db: Session = Depends(get_db)):
    captures = db.query(Capture).filter(Capture.id.in_(body.ids)).all()
    # Commit the row removal before unlinking files. If the commit fails (e.g.
    # read-only DB) we must not have already deleted media for rows that still
    # exist — a failed unlink afterwards leaves a recoverable orphan file, not a
    # dangling row whose image endpoint 404s.
    paths = [os.path.join(settings.DATA_DIR, c.file_path) for c in captures]
    for capture in captures:
        db.delete(capture)
    db.commit()
    for path in paths:
        safe_remove(path)


@router.delete("/captures/{capture_id}", status_code=204)
def delete_capture(capture_id: int, db: Session = Depends(get_db)):
    capture = db.get(Capture, capture_id)
    if not capture:
        raise HTTPException(404, "Capture not found")

    path = os.path.join(settings.DATA_DIR, capture.file_path)
    db.delete(capture)
    db.commit()
    safe_remove(path)
