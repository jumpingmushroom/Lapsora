"""PrusaLink integration: poll a Prusa printer's local HTTP API and drive a
capture profile for the duration of a print (start on PRINTING, stop + generate a
timelapse on FINISHED).

The reconcile decision is a pure state machine (`decide_transition`) so the
print-lifecycle behaviour is testable without a printer, the scheduler, or the DB.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.config import decrypt
from app.database import SessionLocal
from app.models import Profile, Setting
from app.services import events, generation_queue, scheduler

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0)
# Status polls run on a short interval; keep them well under the poll period so an
# offline/slow printer can't make polls overlap (a powered-off printer is normal here).
STATUS_TIMEOUT = httpx.Timeout(5.0)
_DT_FMT = "%Y-%m-%d %H:%M:%S"

DEFAULT_CONFIG = {
    "profile_id": None,
    "poll_interval_seconds": 10,
    "generate_on_finish": True,
    "generate_on_cancel": False,
    "fps": 24,
    "format": "mp4",
    "enabled": True,
}

_EVENT_META = {
    "print_started": ("Print started", "info"),
    "print_finished": ("Print finished", "info"),
    "print_failed": ("Print stopped", "warning"),
}


@dataclass
class PrintDecision:
    """What the poller should do after a single status poll.

    `capturing` is the desired "are we capturing for a print" flag to persist;
    `start_capture`/`stop_capture` are the rising/falling edges that trigger the
    scheduler job add/remove; `generate` requests a timelapse over the print window;
    `event` is the notification event to emit (or None).
    """

    capturing: bool
    start_capture: bool
    stop_capture: bool
    generate: bool
    event: str | None


def normalize_state(raw: str | None) -> str:
    """Map a PrusaLink printer state string to one of: printing, paused, finished, other.

    Everything that isn't an active/paused/successful-finish print (IDLE, READY,
    STOPPED, ERROR, ATTENTION, BUSY, …) collapses to "other".
    """
    s = (raw or "").strip().upper()
    if s == "PRINTING":
        return "printing"
    if s == "PAUSED":
        return "paused"
    if s == "FINISHED":
        return "finished"
    return "other"


def decide_transition(active: bool, state: str, generate_on_cancel: bool = False) -> PrintDecision:
    """Pure reconcile: given whether we're currently capturing for a print (`active`)
    and the normalized polled `state`, decide the side effects to perform."""
    if state == "printing":
        if not active:
            return PrintDecision(True, start_capture=True, stop_capture=False, generate=False, event="print_started")
        return PrintDecision(True, start_capture=False, stop_capture=False, generate=False, event=None)
    if state == "paused":
        # Keep capturing if we already were; don't begin a fresh capture on a paused print.
        return PrintDecision(active, start_capture=False, stop_capture=False, generate=False, event=None)
    if state == "finished":
        if active:
            return PrintDecision(False, start_capture=False, stop_capture=True, generate=True, event="print_finished")
        return PrintDecision(False, start_capture=False, stop_capture=False, generate=False, event=None)
    # "other": idle/stopped/error/etc. If a print was in progress, treat as cancelled.
    if active:
        return PrintDecision(False, start_capture=False, stop_capture=True, generate=generate_on_cancel, event="print_failed")
    return PrintDecision(False, start_capture=False, stop_capture=False, generate=False, event=None)


# --- status parsing + HTTP -------------------------------------------------


def parse_status(data: dict) -> dict:
    """Extract the bits we care about from a PrusaLink /api/v1/status response."""
    printer = (data or {}).get("printer") or {}
    job = (data or {}).get("job") or {}
    return {
        "state": printer.get("state"),
        "job_id": job.get("id"),
        "progress": job.get("progress"),
    }


def _auth(username: str, password: str) -> httpx.DigestAuth:
    return httpx.DigestAuth(username or "maker", password or "")


HEALTH_TIMEOUT = httpx.Timeout(3.0)  # short probe for the settings badge


async def health(base_url: str, username: str, password: str) -> bool:
    """Quick reachability + auth probe for the settings status badge."""
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            resp = await client.get(f"{base}/api/v1/status", auth=_auth(username, password))
        return resp.status_code == 200
    except Exception:
        return False


async def test_connection(base_url: str, username: str, password: str) -> dict:
    """Validate reachability + auth against PrusaLink's /api/v1/status."""
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"{base}/api/v1/status", auth=_auth(username, password))
        if resp.status_code == 200:
            return {"success": True, "message": "Connected"}
        if resp.status_code in (401, 403):
            return {"success": False, "message": "Unauthorized — check username/password"}
        return {"success": False, "message": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


async def get_status(base_url: str, username: str, password: str) -> dict | None:
    """Fetch + parse the printer status, or None if unreachable."""
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=STATUS_TIMEOUT) as client:
            resp = await client.get(f"{base}/api/v1/status", auth=_auth(username, password))
            resp.raise_for_status()
            return parse_status(resp.json())
    except Exception as exc:
        # An offline/unreachable printer is expected (printers are often powered off);
        # log quietly without a traceback. Test Connection surfaces config errors loudly.
        logger.debug("PrusaLink status poll failed for %s: %s", base, exc)
        return None


# --- config + persisted state ----------------------------------------------


def _get_setting(db, key: str) -> str | None:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


def _set_setting(db, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


def get_config(db) -> dict | None:
    """Return the merged PrusaLink config (incl. decrypted password), or None if unset."""
    base = _get_setting(db, "prusalink_base_url")
    if not base:
        return None
    cfg = DEFAULT_CONFIG.copy()
    blob = _get_setting(db, "prusalink_config")
    if blob:
        try:
            cfg.update(json.loads(blob))
        except (json.JSONDecodeError, TypeError):
            pass
    cfg["base_url"] = base
    cfg["username"] = _get_setting(db, "prusalink_username") or "maker"
    pw = _get_setting(db, "prusalink_password")
    password = ""
    if pw:
        try:
            password = decrypt(pw)
        except Exception:
            logger.warning("Failed to decrypt PrusaLink password")
    cfg["password"] = password
    return cfg


def _parse_started_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, _DT_FMT).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


# --- reconcile + poll ------------------------------------------------------


async def _reconcile(db, cfg: dict, raw_state: str | None) -> PrintDecision:
    """Apply the side effects implied by a single polled state."""
    active = _get_setting(db, "prusalink_active") == "true"
    state = normalize_state(raw_state)
    d = decide_transition(active, state, cfg.get("generate_on_cancel", False))
    profile = db.get(Profile, cfg["profile_id"]) if cfg.get("profile_id") else None

    if d.start_capture and profile:
        profile.enabled = True
        db.commit()
        scheduler.add_capture_job(profile)
        _set_setting(db, "prusalink_active", "true")
        _set_setting(db, "prusalink_print_started_at", datetime.now(UTC).strftime(_DT_FMT))
        db.commit()

    if d.stop_capture and profile:
        scheduler.remove_capture_job(profile.id)
        profile.enabled = False
        db.commit()

    # Honour the generate_on_finish toggle (cancel is already gated inside decide_transition).
    should_generate = d.generate
    if d.event == "print_finished" and not cfg.get("generate_on_finish", True):
        should_generate = False
    if should_generate and profile:
        start = _parse_started_at(_get_setting(db, "prusalink_print_started_at")) or (
            datetime.now(UTC) - timedelta(hours=24)
        )
        await generation_queue.enqueue_generation(
            profile_id=profile.id,
            period_type="custom",
            period_start=start,
            period_end=datetime.now(UTC),
            fps=cfg.get("fps", 24),
            format=cfg.get("format", "mp4"),
            timestamp_overlay=True,
        )

    if d.stop_capture:
        _set_setting(db, "prusalink_active", "false")
        _set_setting(db, "prusalink_print_started_at", "")
        db.commit()

    if d.event:
        title, level = _EVENT_META.get(d.event, (d.event, "info"))
        name = profile.name if profile else "print"
        await events.emit(d.event, title, f"{title}: {name}", level=level)

    return d


async def poll_printer() -> None:
    """Scheduled job: poll PrusaLink and reconcile the print lifecycle."""
    db = SessionLocal()
    try:
        cfg = get_config(db)
        if not cfg or not cfg.get("enabled", True) or not cfg.get("profile_id"):
            return
        status = await get_status(cfg["base_url"], cfg["username"], cfg["password"])
        if not status or not status.get("state"):
            return
        await _reconcile(db, cfg, status["state"])
    except Exception:
        logger.exception("PrusaLink poll failed")
    finally:
        db.rollback()
        db.close()
