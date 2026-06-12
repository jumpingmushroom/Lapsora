"""Stream management endpoints."""

import os
import shutil

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import encrypt, settings
from app.database import get_db
from app.models import Stream
from app.schemas import StreamCreate, StreamRead, StreamUpdate
from app.services import go2rtc, providers

router = APIRouter(prefix="/api/streams", tags=["streams"])


@router.get("/", response_model=list[StreamRead])
def list_streams(db: Session = Depends(get_db)):
    return db.query(Stream).order_by(Stream.id).all()


@router.get("/go2rtc/discover")
async def discover_go2rtc_streams(db: Session = Depends(get_db)):
    base_url = go2rtc.get_go2rtc_url(db)
    if not base_url:
        raise HTTPException(400, "go2rtc URL not configured")
    try:
        return await go2rtc.list_streams(base_url)
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch go2rtc streams: {exc}")


@router.post("/", response_model=StreamRead, status_code=201)
def create_stream(body: StreamCreate, db: Session = Depends(get_db)):
    if body.source_type == "go2rtc":
        if not body.go2rtc_name:
            raise HTTPException(400, "go2rtc_name is required for go2rtc streams")
        stream = Stream(
            name=body.name,
            url=encrypt(""),
            source_type="go2rtc",
            go2rtc_name=body.go2rtc_name,
        )
    else:
        # rtsp, http_snapshot, http_mjpeg all need a URL.
        if not body.url:
            raise HTTPException(400, "url is required for this source type")
        stream = Stream(
            name=body.name,
            url=encrypt(body.url),
            source_type=body.source_type,
            auth_type=body.auth_type or "none",
            auth_username=body.auth_username,
            auth_secret=encrypt(body.auth_secret) if body.auth_secret else None,
            auth_header_name=body.auth_header_name,
        )
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream


@router.get("/{stream_id}", response_model=StreamRead)
def get_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    return stream


@router.put("/{stream_id}", response_model=StreamRead)
def update_stream(stream_id: int, body: StreamUpdate, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    if body.name is not None:
        stream.name = body.name
    if body.url is not None:
        stream.url = encrypt(body.url)
    if body.enabled is not None:
        stream.enabled = body.enabled
    if body.auth_type is not None:
        stream.auth_type = body.auth_type
    if body.auth_username is not None:
        stream.auth_username = body.auth_username
    if body.auth_secret is not None:
        # Empty string clears the stored secret; otherwise encrypt and store.
        stream.auth_secret = encrypt(body.auth_secret) if body.auth_secret else None
    if body.auth_header_name is not None:
        stream.auth_header_name = body.auth_header_name

    db.commit()
    db.refresh(stream)
    return stream


@router.delete("/{stream_id}", status_code=204)
def delete_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    # Commit the cascade delete first, then tear down scheduler jobs. Doing the
    # irreversible job removal only after a successful commit avoids leaving
    # still-present profiles without their capture jobs if the commit fails.
    profile_ids = [profile.id for profile in stream.profiles]

    db.delete(stream)
    db.commit()

    from app.services.scheduler import remove_capture_job
    for pid in profile_ids:
        remove_capture_job(pid)

    # Remove media files. The DB cascade already dropped the capture/timelapse
    # rows, so the orphan sweep can't reclaim these — delete the directories by
    # their deterministic paths (captures/<stream_id>/ covers all profiles).
    capture_dir = os.path.join(settings.DATA_DIR, "captures", str(stream_id))
    if os.path.isdir(capture_dir):
        shutil.rmtree(capture_dir, ignore_errors=True)
    for pid in profile_ids:
        timelapse_dir = os.path.join(settings.DATA_DIR, "timelapses", str(pid))
        if os.path.isdir(timelapse_dir):
            shutil.rmtree(timelapse_dir, ignore_errors=True)


@router.post("/{stream_id}/test")
async def test_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    return await providers.test_source(stream, db)


@router.get("/{stream_id}/preview")
async def preview_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    try:
        jpeg_bytes = await providers.grab_preview(stream, db)
    except Exception as exc:
        raise HTTPException(502, str(exc))
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@router.get("/{stream_id}/ir-test")
async def ir_test_stream(stream_id: int, db: Session = Depends(get_db)):
    """Grab a live frame and report its measured chroma + a base64 thumbnail.

    Used by the profile form to dial in the IR-only threshold: sample once in
    daylight and once at night, then set the threshold between the two values.
    """
    import base64
    import io

    from PIL import Image

    from app.services.ir_detect import mean_chroma

    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    try:
        jpeg_bytes = await providers.grab_preview(stream, db)
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch frame: {exc}")

    with Image.open(io.BytesIO(jpeg_bytes)) as img:
        chroma = mean_chroma(img)

    return {
        "chroma": round(chroma, 1),
        "preview": base64.b64encode(jpeg_bytes).decode("ascii"),
    }


@router.get("/{stream_id}/live-url")
def get_live_url(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    if stream.source_type != "go2rtc":
        raise HTTPException(400, "Live view is only available for go2rtc streams")

    base_url = go2rtc.get_go2rtc_url(db)
    if not base_url:
        raise HTTPException(400, "go2rtc URL not configured")

    # Convert http(s) to ws(s) for WebSocket URL
    ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
    return {"ws_url": f"{ws_url}/api/ws?src={stream.go2rtc_name}"}
