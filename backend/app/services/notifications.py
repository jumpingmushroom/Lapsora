"""Notification service — persists notifications, pushes SSE, sends via Apprise."""

import asyncio
import json
import logging
from typing import Any

import apprise

from app.config import decrypt
from app.database import SessionLocal
from app.models import Notification, NotificationURL, Setting

logger = logging.getLogger(__name__)

# SSE client queues — one asyncio.Queue per connected browser client
sse_queues: list[asyncio.Queue] = []

# Default event toggles
DEFAULT_EVENT_TOGGLES = {
    "capture_failure": True,
    "stream_unhealthy": True,
    "stream_recovered": True,
    "timelapse_complete": True,
    "timelapse_failure": True,
    "retention_summary": False,
    "low_disk_space": True,
}


def _get_event_toggles(db: Any) -> dict:
    """Load notification event toggles from settings table."""
    row = db.query(Setting).filter(Setting.key == "notification_events").first()
    if row:
        try:
            return json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            pass
    return DEFAULT_EVENT_TOGGLES.copy()


async def handle_event(event_type: str, title: str, body: str, level: str = "info") -> None:
    """Event listener registered on the event bus. Persists, broadcasts SSE, sends Apprise."""
    db = SessionLocal()
    try:
        # 1. Always persist to notifications table
        notification = Notification(
            event_type=event_type,
            title=title,
            body=body,
            level=level,
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)

        # 2. Push to SSE queues
        sse_data = json.dumps({
            "id": notification.id,
            "event_type": event_type,
            "title": title,
            "body": body,
            "level": level,
            "created_at": notification.created_at.isoformat(),
        })
        for queue in list(sse_queues):
            try:
                queue.put_nowait(sse_data)
            except asyncio.QueueFull:
                pass

        # 3. Check if this event type is enabled for external delivery
        toggles = _get_event_toggles(db)
        if not toggles.get(event_type, False):
            return

        # 4. Send via Apprise to all enabled notification URLs
        urls = db.query(NotificationURL).filter(NotificationURL.enabled.is_(True)).all()
        if not urls:
            return

        ap = apprise.Apprise()
        for nu in urls:
            try:
                ap.add(decrypt(nu.url))
            except Exception:
                logger.warning("Failed to decrypt/add notification URL %d", nu.id)

        if len(ap) > 0:
            level_map = {"info": apprise.NotifyType.INFO, "warning": apprise.NotifyType.WARNING, "error": apprise.NotifyType.FAILURE}
            notify_type = level_map.get(level, apprise.NotifyType.INFO)
            await asyncio.to_thread(ap.notify, title=title, body=body, notify_type=notify_type)

    except Exception:
        logger.exception("Notification handling failed for event %s", event_type)
    finally:
        db.close()


async def send_test_notification(url_id: int) -> bool:
    """Send a test notification to a specific URL."""
    db = SessionLocal()
    try:
        nu = db.query(NotificationURL).filter(NotificationURL.id == url_id).first()
        if not nu:
            return False

        ap = apprise.Apprise()
        try:
            ap.add(decrypt(nu.url))
        except Exception:
            return False

        result = await asyncio.to_thread(
            ap.notify,
            title="Lapsora Test Notification",
            body="This is a test notification from Lapsora.",
            notify_type=apprise.NotifyType.INFO,
        )
        return result
    finally:
        db.close()
