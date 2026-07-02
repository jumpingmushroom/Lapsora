"""Settings API endpoints for notifications and health monitoring."""

import json
import logging
import os
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from app.config import decrypt, encrypt
from app.config import settings as app_settings
from app.database import get_db
from app.models import NotificationURL, PrintJob, Profile, Setting
from app.schemas import (
    CaptureGapUpdate,
    Go2rtcConfig,
    HealthConfig,
    HomeAssistantConfig,
    LocationConfig,
    NotificationEventsConfig,
    NotificationURLCreate,
    NotificationURLRead,
    NotificationURLUpdate,
    PrusaLinkConfig,
    PrusaLinkRead,
    TimeFormatConfig,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


# --- Notification URLs ---


@router.get("/notifications", response_model=dict)
def get_notification_settings(db: Session = Depends(get_db)):
    urls = db.query(NotificationURL).all()
    url_list = [NotificationURLRead.model_validate(u).model_dump() for u in urls]

    row = db.query(Setting).filter(Setting.key == "notification_events").first()
    if row:
        try:
            events = json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            events = NotificationEventsConfig().model_dump()
    else:
        events = NotificationEventsConfig().model_dump()

    return {"urls": url_list, "events": events}


@router.post("/notifications/urls", response_model=NotificationURLRead, status_code=201)
def add_notification_url(data: NotificationURLCreate, db: Session = Depends(get_db)):
    nu = NotificationURL(label=data.label, url=encrypt(data.url))
    db.add(nu)
    db.commit()
    db.refresh(nu)
    return nu


@router.put("/notifications/urls/{url_id}", response_model=NotificationURLRead)
def update_notification_url(url_id: int, data: NotificationURLUpdate, db: Session = Depends(get_db)):
    nu = db.query(NotificationURL).filter(NotificationURL.id == url_id).first()
    if not nu:
        raise HTTPException(404, "Notification URL not found")
    if data.label is not None:
        nu.label = data.label
    if data.enabled is not None:
        nu.enabled = data.enabled
    db.commit()
    db.refresh(nu)
    return nu


@router.delete("/notifications/urls/{url_id}", status_code=204)
def delete_notification_url(url_id: int, db: Session = Depends(get_db)):
    nu = db.query(NotificationURL).filter(NotificationURL.id == url_id).first()
    if not nu:
        raise HTTPException(404, "Notification URL not found")
    db.delete(nu)
    db.commit()


@router.post("/notifications/urls/{url_id}/test")
async def test_notification_url(url_id: int, db: Session = Depends(get_db)):
    nu = db.query(NotificationURL).filter(NotificationURL.id == url_id).first()
    if not nu:
        raise HTTPException(404, "Notification URL not found")

    from app.services.notifications import send_test_notification
    success = await send_test_notification(url_id)
    return {"success": success}


@router.put("/notifications/events")
def update_event_toggles(data: NotificationEventsConfig, db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == "notification_events").first()
    value = json.dumps(data.model_dump())
    if row:
        row.value = value
    else:
        db.add(Setting(key="notification_events", value=value))
    db.commit()
    return data.model_dump()


# --- Location Config ---


@router.get("/location", response_model=LocationConfig)
def get_location_config(db: Session = Depends(get_db)):
    config = LocationConfig()
    for field in config.model_fields:
        key = f"location_{field}"
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            try:
                setattr(config, field, float(row.value))
            except (ValueError, TypeError):
                pass
    return config


@router.put("/location", response_model=LocationConfig)
def update_location_config(data: LocationConfig, db: Session = Depends(get_db)):
    for field, value in data.model_dump().items():
        key = f"location_{field}"
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = str(value)
        else:
            db.add(Setting(key=key, value=str(value)))
    db.commit()
    return data


# --- Health Config ---


@router.get("/health", response_model=HealthConfig)
def get_health_config(db: Session = Depends(get_db)):
    config = HealthConfig()
    for field in config.model_fields:
        key = f"health_{field}"
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            try:
                setattr(config, field, int(row.value))
            except (ValueError, TypeError):
                pass
    return config


@router.put("/health", response_model=HealthConfig)
def update_health_config(data: HealthConfig, db: Session = Depends(get_db)):
    for field, value in data.model_dump().items():
        key = f"health_{field}"
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = str(value)
        else:
            db.add(Setting(key=key, value=str(value)))

    # Also store the failure threshold under the key used by health service
    threshold_row = db.query(Setting).filter(Setting.key == "health_check_failure_threshold").first()
    if threshold_row:
        threshold_row.value = str(data.failure_threshold)
    else:
        db.add(Setting(key="health_check_failure_threshold", value=str(data.failure_threshold)))

    db.commit()
    return data


# --- go2rtc Config ---


@router.get("/go2rtc")
async def get_go2rtc_config(db: Session = Depends(get_db)):
    from app.services import go2rtc, health_status
    row = db.query(Setting).filter(Setting.key == "go2rtc_url").first()
    url = row.value if row else ""
    connected = await health_status.reachable("go2rtc", lambda: go2rtc.health(url)) if url else False
    return {"url": url, "configured": bool(url), "connected": connected}


@router.put("/go2rtc")
def update_go2rtc_config(data: Go2rtcConfig, db: Session = Depends(get_db)):
    from app.services import health_status
    url = data.url.rstrip("/")
    row = db.query(Setting).filter(Setting.key == "go2rtc_url").first()
    if row:
        row.value = url
    else:
        db.add(Setting(key="go2rtc_url", value=url))
    db.commit()
    health_status.invalidate("go2rtc")
    return {"url": url}


@router.post("/go2rtc/test")
async def test_go2rtc_server(data: Go2rtcConfig):
    from app.services.go2rtc import test_server
    return await test_server(data.url.rstrip("/"))


# --- Capture Gap Alerting ---


@router.get("/capture-gap")
def get_capture_gap_config(db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == "capture_gap_enabled").first()
    enabled = True if not row else row.value != "false"
    return {"enabled": enabled}


@router.put("/capture-gap")
def update_capture_gap_config(data: CaptureGapUpdate, db: Session = Depends(get_db)):
    enabled = data.enabled
    row = db.query(Setting).filter(Setting.key == "capture_gap_enabled").first()
    value = "true" if enabled else "false"
    if row:
        row.value = value
    else:
        db.add(Setting(key="capture_gap_enabled", value=value))
    db.commit()

    from app.services.scheduler import add_capture_gap_job, remove_capture_gap_job
    if enabled:
        add_capture_gap_job()
    else:
        remove_capture_gap_job()

    return {"enabled": enabled}


# --- Time Format Config ---


@router.get("/time-format", response_model=TimeFormatConfig)
def get_time_format_config(db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == "time_format_use_24h").first()
    use_24h = row is not None and row.value == "true"
    return TimeFormatConfig(use_24h=use_24h)


@router.put("/time-format", response_model=TimeFormatConfig)
def update_time_format_config(data: TimeFormatConfig, db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == "time_format_use_24h").first()
    value = "true" if data.use_24h else "false"
    if row:
        row.value = value
    else:
        db.add(Setting(key="time_format_use_24h", value=value))
    db.commit()
    return data


# --- Home Assistant ---


def _upsert_setting(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


async def _read_ha(db: Session) -> dict:
    """base_url + configured (creds present) + connected (cached live probe)."""
    from app.services import health_status, homeassistant
    url_row = db.query(Setting).filter(Setting.key == "ha_base_url").first()
    base_url = url_row.value if url_row else ""
    cfg = homeassistant.get_ha_config(db)  # (base_url, token) or None
    configured = cfg is not None
    connected = await health_status.reachable("ha", lambda: homeassistant.health(*cfg)) if configured else False
    return {"base_url": base_url, "configured": configured, "connected": connected}


@router.get("/homeassistant")
async def get_ha_settings(db: Session = Depends(get_db)):
    return await _read_ha(db)


@router.put("/homeassistant")
async def update_ha_settings(data: HomeAssistantConfig, db: Session = Depends(get_db)):
    from app.services import health_status
    url = data.base_url.rstrip("/")
    _upsert_setting(db, "ha_base_url", url)
    if data.token:  # only overwrite token when a new one is supplied
        _upsert_setting(db, "ha_token", encrypt(data.token))
    db.commit()
    health_status.invalidate("ha")
    return await _read_ha(db)


@router.post("/homeassistant/test")
async def test_ha_connection(data: HomeAssistantConfig, db: Session = Depends(get_db)):
    from app.services.homeassistant import test_connection
    token = data.token
    if not token:  # fall back to the stored token
        tok_row = db.query(Setting).filter(Setting.key == "ha_token").first()
        token = decrypt(tok_row.value) if tok_row and tok_row.value else ""
    return await test_connection(data.base_url.rstrip("/"), token)


@router.get("/homeassistant/entities")
async def get_ha_entities(db: Session = Depends(get_db)):
    from app.services.homeassistant import get_ha_config, list_sensor_entities
    cfg = get_ha_config(db)
    if not cfg:
        raise HTTPException(400, "Home Assistant not configured")
    return await list_sensor_entities(*cfg)


# --- PrusaLink (3D-print timelapse trigger) ---

_PRUSALINK_BLOB_FIELDS = (
    "stream_id", "poll_interval_seconds", "generate_on_finish", "generate_on_cancel",
    "enabled", "clip_seconds", "clip_fps", "default_interval_seconds",
    "min_interval_seconds", "max_interval_seconds",
    "timestamp_overlay", "logo_overlay", "deflicker", "quality", "ha_sensors",
)


def _read_prusalink(db: Session) -> dict:
    base = db.query(Setting).filter(Setting.key == "prusalink_base_url").first()
    user = db.query(Setting).filter(Setting.key == "prusalink_username").first()
    pw = db.query(Setting).filter(Setting.key == "prusalink_password").first()
    blob_row = db.query(Setting).filter(Setting.key == "prusalink_config").first()
    cfg = {f: getattr(PrusaLinkConfig.model_fields[f], "default") for f in _PRUSALINK_BLOB_FIELDS}
    if blob_row:
        try:
            cfg.update({k: v for k, v in json.loads(blob_row.value).items() if k in _PRUSALINK_BLOB_FIELDS})
        except (json.JSONDecodeError, TypeError):
            pass
    cfg["base_url"] = base.value if base else ""
    cfg["username"] = user.value if user else "maker"
    cfg["configured"] = bool((base and base.value) and (pw and pw.value))
    return cfg


async def _read_prusalink_live(db: Session) -> dict:
    """`_read_prusalink` + a cached live reachability probe for the badge."""
    from app.services import health_status, prusalink
    cfg = _read_prusalink(db)
    pcfg = prusalink.get_config(db)  # includes decrypted password, or None
    if cfg["configured"] and pcfg:
        cfg["connected"] = await health_status.reachable(
            "prusalink",
            lambda: prusalink.health(pcfg["base_url"], pcfg["username"], pcfg["password"]),
        )
    else:
        cfg["connected"] = False
    return cfg


@router.get("/prusalink", response_model=PrusaLinkRead)
async def get_prusalink_settings(db: Session = Depends(get_db)):
    return await _read_prusalink_live(db)


@router.put("/prusalink", response_model=PrusaLinkRead)
async def update_prusalink_settings(data: PrusaLinkConfig, db: Session = Depends(get_db)):
    url = data.base_url.rstrip("/")
    _upsert_setting(db, "prusalink_base_url", url)
    _upsert_setting(db, "prusalink_username", data.username or "maker")
    if data.password:  # only overwrite when a new one is supplied
        _upsert_setting(db, "prusalink_password", encrypt(data.password))
    blob = {f: getattr(data, f) for f in _PRUSALINK_BLOB_FIELDS}
    _upsert_setting(db, "prusalink_config", json.dumps(blob))
    db.commit()

    from app.services import health_status, prusalink
    from app.services.scheduler import add_prusalink_poll_job, remove_capture_job, remove_prusalink_poll_job

    cfg = prusalink.get_config(db)
    if cfg:
        prusalink.ensure_managed_profile(db, cfg)
    if data.enabled and url and data.stream_id:
        add_prusalink_poll_job(data.poll_interval_seconds)
    else:
        remove_prusalink_poll_job()
        # The poll job is gone, so no further reconcile will ever close out an
        # in-flight print. Close it here to avoid an orphaned 'printing' row
        # and a managed profile stuck enabled with no way to disable it via
        # the (hidden) profiles UI.
        open_pj = db.query(PrintJob).filter(PrintJob.status == "printing").first()
        if open_pj:
            managed_profile = db.query(Profile).filter(Profile.managed_by == "prusalink").first()
            if managed_profile:
                remove_capture_job(managed_profile.id)
                managed_profile.enabled = False
            open_pj.status = "cancelled"
            open_pj.finished_at = datetime.now(UTC)
            db.commit()

    health_status.invalidate("prusalink")
    return await _read_prusalink_live(db)


@router.post("/prusalink/test")
async def test_prusalink_connection(data: PrusaLinkConfig, db: Session = Depends(get_db)):
    from app.services.prusalink import test_connection
    password = data.password
    if not password:  # fall back to stored password
        pw_row = db.query(Setting).filter(Setting.key == "prusalink_password").first()
        password = decrypt(pw_row.value) if pw_row and pw_row.value else ""
    return await test_connection(data.base_url.rstrip("/"), data.username or "maker", password)


# --- Logo / watermark ---

LOGO_DIR = Path(app_settings.DATA_DIR) / "logos"
LOGO_PATH = LOGO_DIR / "logo.png"


def _logo_info(db: Session) -> dict:
    row = db.query(Setting).filter(Setting.key == "logo_file_path").first()
    if row and os.path.exists(row.value):
        mtime = datetime.fromtimestamp(os.path.getmtime(row.value), UTC)
        return {"exists": True, "uploaded_at": mtime.isoformat()}
    return {"exists": False, "uploaded_at": None}


@router.get("/logo")
def get_logo(db: Session = Depends(get_db)):
    return _logo_info(db)


@router.post("/logo")
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    try:
        Image.open(BytesIO(data)).verify()
        img = Image.open(BytesIO(data)).convert("RGBA")
    except Exception:
        raise HTTPException(400, "Uploaded file is not a valid image")
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    img.save(LOGO_PATH, "PNG")
    _upsert_setting(db, "logo_file_path", str(LOGO_PATH))
    db.commit()
    return _logo_info(db)


@router.delete("/logo", status_code=204)
def delete_logo(db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == "logo_file_path").first()
    if row:
        if os.path.exists(row.value):
            try:
                os.unlink(row.value)
            except OSError:
                pass
        db.delete(row)
        db.commit()
