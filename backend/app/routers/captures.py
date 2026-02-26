"""Capture management endpoints."""

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Capture
from app.schemas import CaptureRead

router = APIRouter(prefix="/api", tags=["captures"])


@router.get("/profiles/{profile_id}/captures", response_model=list[CaptureRead])
def list_captures(
    profile_id: int,
    limit: int = 50,
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


@router.delete("/captures/{capture_id}", status_code=204)
def delete_capture(capture_id: int, db: Session = Depends(get_db)):
    capture = db.get(Capture, capture_id)
    if not capture:
        raise HTTPException(404, "Capture not found")

    # Remove file
    abs_path = os.path.join(settings.DATA_DIR, capture.file_path)
    if os.path.isfile(abs_path):
        os.remove(abs_path)

    db.delete(capture)
    db.commit()
