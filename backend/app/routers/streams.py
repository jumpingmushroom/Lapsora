"""Stream management endpoints."""

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import decrypt, encrypt
from app.database import get_db
from app.models import Setting, Stream
from app.schemas import StreamCreate, StreamRead, StreamUpdate
from app.services import rtsp
from app.services import go2rtc

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
        if not body.url:
            raise HTTPException(400, "url is required for RTSP streams")
        stream = Stream(name=body.name, url=encrypt(body.url), source_type="rtsp")
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

    db.commit()
    db.refresh(stream)
    return stream


@router.delete("/{stream_id}", status_code=204)
def delete_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    db.delete(stream)
    db.commit()


@router.post("/{stream_id}/test")
async def test_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    if stream.source_type == "go2rtc":
        base_url = go2rtc.get_go2rtc_url(db)
        if not base_url:
            raise HTTPException(400, "go2rtc URL not configured")
        return await go2rtc.test_stream(base_url, stream.go2rtc_name)

    try:
        url = decrypt(stream.url)
    except (InvalidToken, Exception):
        raise HTTPException(400, "Stream URL could not be decrypted. Please re-enter the RTSP URL.")
    return await rtsp.test_connection(url)


@router.get("/{stream_id}/preview")
async def preview_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    if stream.source_type == "go2rtc":
        base_url = go2rtc.get_go2rtc_url(db)
        if not base_url:
            raise HTTPException(400, "go2rtc URL not configured")
        try:
            jpeg_bytes = await go2rtc.grab_frame(base_url, stream.go2rtc_name)
        except Exception as exc:
            raise HTTPException(502, str(exc))
        return Response(content=jpeg_bytes, media_type="image/jpeg")

    try:
        url = decrypt(stream.url)
    except (InvalidToken, Exception):
        raise HTTPException(400, "Stream URL could not be decrypted. Please re-enter the RTSP URL.")
    try:
        jpeg_bytes = await rtsp.grab_frame(url)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    return Response(content=jpeg_bytes, media_type="image/jpeg")


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
