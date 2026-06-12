"""Capture management endpoints."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Capture
from app.schemas import BulkDeleteRequest, CaptureRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["captures"])


def _safe_remove(path: str) -> None:
    """Remove a file, logging (not raising) on failure so a single bad file
    never aborts a delete that must still purge the DB rows."""
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        logger.exception("Failed to remove file %s during delete", path)


@router.get("/profiles/{profile_id}/captures", response_model=list[CaptureRead])
def list_captures(
    profile_id: int,
    limit: int = Query(default=50, le=1000),
    offset: int = 0,
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
    for capture in captures:
        _safe_remove(os.path.join(settings.DATA_DIR, capture.file_path))
        db.delete(capture)
    db.commit()


@router.delete("/captures/{capture_id}", status_code=204)
def delete_capture(capture_id: int, db: Session = Depends(get_db)):
    capture = db.get(Capture, capture_id)
    if not capture:
        raise HTTPException(404, "Capture not found")

    _safe_remove(os.path.join(settings.DATA_DIR, capture.file_path))
    db.delete(capture)
    db.commit()
