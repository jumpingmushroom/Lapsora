"""Settings API endpoints for notifications and health monitoring."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import encrypt
from app.database import get_db
from app.models import NotificationURL, Setting
from app.schemas import (
    HealthConfig,
    LocationConfig,
    NotificationEventsConfig,
    NotificationURLCreate,
    NotificationURLRead,
    NotificationURLUpdate,
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
