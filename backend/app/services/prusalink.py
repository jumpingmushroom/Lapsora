"""PrusaLink integration: poll a Prusa printer's local HTTP API and drive a
capture profile for the duration of a print (start on PRINTING, stop + generate a
timelapse on FINISHED).

The reconcile decision is a pure state machine (`decide_transition`) so the
print-lifecycle behaviour is testable without a printer, the scheduler, or the DB.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.config import decrypt
from app.database import SessionLocal
from app.models import PrintJob, Profile, Setting
from app.services import events, generation_queue, scheduler

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0)
# Status polls run on a short interval; keep them well under the poll period so an
# offline/slow printer can't make polls overlap (a powered-off printer is normal here).
STATUS_TIMEOUT = httpx.Timeout(5.0)

DEFAULT_CONFIG = {
    "stream_id": None,
    "poll_interval_seconds": 10,
    "generate_on_finish": True,
    "generate_on_cancel": False,
    "enabled": True,
    "clip_seconds": 20,
    "clip_fps": 25,
    "default_interval_seconds": 10,
    "min_interval_seconds": 2,
    "max_interval_seconds": 120,
    "timestamp_overlay": True,
    "logo_overlay": False,
    "deflicker": "medium",
    "quality": 90,
    "ha_sensors": None,
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


def compute_interval(
    estimated_seconds: float | None,
    clip_seconds: int,
    clip_fps: int,
    default_interval: int,
    min_interval: int,
    max_interval: int,
) -> int:
    """Capture interval so a print of the estimated length yields roughly
    clip_seconds x clip_fps frames. Missing/bogus estimate -> default. Always
    clamped to [min_interval, max_interval]."""
    if not estimated_seconds or estimated_seconds <= 0:
        interval = default_interval
    else:
        target_frames = max(1, clip_seconds * clip_fps)
        interval = round(estimated_seconds / target_frames)
    return int(max(min_interval, min(max_interval, interval)))


# --- status parsing + HTTP -------------------------------------------------


def parse_status(data: dict) -> dict:
    """Extract the bits we care about from a PrusaLink /api/v1/status response."""
    printer = (data or {}).get("printer") or {}
    job = (data or {}).get("job") or {}
    file_info = job.get("file") or {}
    remaining = job.get("time_remaining")
    printing = job.get("time_printing")
    estimated = None
    if isinstance(remaining, (int, float)) and remaining > 0:
        estimated = float(remaining)
        if isinstance(printing, (int, float)) and printing > 0:
            estimated += float(printing)
    return {
        "state": printer.get("state"),
        "job_id": job.get("id"),
        "progress": job.get("progress"),
        "gcode_name": file_info.get("display_name") or file_info.get("name"),
        "estimated_seconds": estimated,
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


MANAGED_PROFILE_NAME = "3D Print (auto)"


def ensure_managed_profile(db, cfg: dict):
    """Find-or-create the integration-owned capture profile and sync it to the
    current settings. There is at most one; it is hidden from the profiles UI
    and its interval is rewritten per print."""
    stream_id = cfg.get("stream_id")
    if not stream_id:
        return None
    is_new = False
    profile = db.query(Profile).filter(Profile.managed_by == "prusalink").first()
    if profile is None:
        is_new = True
        profile = Profile(
            name=MANAGED_PROFILE_NAME,
            managed_by="prusalink",
            enabled=False,
            interval_seconds=cfg.get("default_interval_seconds", 10),
        )
        db.add(profile)

    # Called on every poll (~10s) while a print is active; only write when a
    # target field actually changed to avoid a needless DB write each poll.
    targets = {
        "stream_id": stream_id,
        "quality": cfg.get("quality", 90),
        "ha_sensors": cfg.get("ha_sensors") or None,
        "fps_mode": "target_duration",
        "render_target_seconds": cfg.get("clip_seconds", 20),
        "render_fps": cfg.get("clip_fps", 25),
    }
    if is_new or any(getattr(profile, field) != value for field, value in targets.items()):
        for field, value in targets.items():
            setattr(profile, field, value)
        db.commit()
    return profile


# --- reconcile + poll ------------------------------------------------------


def _open_print_job(db):
    return (
        db.query(PrintJob)
        .filter(PrintJob.status == "printing")
        .order_by(PrintJob.id.desc())
        .first()
    )


def _apply_interval(db, profile, pj, interval: int, *, reschedule: bool) -> None:
    pj.interval_seconds = interval
    profile.interval_seconds = interval
    db.commit()
    if reschedule:
        scheduler.reschedule_capture_job(profile)


async def _reconcile(db, cfg: dict, status: dict) -> PrintDecision:
    """Apply the side effects implied by a single polled status."""
    pj = _open_print_job(db)
    state = normalize_state(status.get("state"))
    d = decide_transition(pj is not None, state, cfg.get("generate_on_cancel", False))

    profile = None
    if d.start_capture or pj is not None:
        profile = ensure_managed_profile(db, cfg)

    if d.start_capture and profile:
        interval = compute_interval(
            status.get("estimated_seconds"),
            cfg["clip_seconds"], cfg["clip_fps"],
            cfg["default_interval_seconds"],
            cfg["min_interval_seconds"], cfg["max_interval_seconds"],
        )
        pj = PrintJob(
            prusalink_job_id=status.get("job_id"),
            gcode_name=status.get("gcode_name") or "",
            stream_id=profile.stream_id,
            status="printing",
            started_at=datetime.now(UTC),
            estimated_seconds=status.get("estimated_seconds"),
            interval_seconds=interval,
        )
        db.add(pj)
        profile.enabled = True
        profile.interval_seconds = interval
        db.commit()
        scheduler.add_capture_job(profile)

    elif pj and state == "printing" and profile:
        # Recompute once: the print started before PrusaLink knew its length.
        if pj.estimated_seconds is None and status.get("estimated_seconds"):
            pj.estimated_seconds = status["estimated_seconds"]
            interval = compute_interval(
                pj.estimated_seconds,
                cfg["clip_seconds"], cfg["clip_fps"],
                cfg["default_interval_seconds"],
                cfg["min_interval_seconds"], cfg["max_interval_seconds"],
            )
            _apply_interval(db, profile, pj, interval, reschedule=True)
        if not pj.gcode_name and status.get("gcode_name"):
            pj.gcode_name = status["gcode_name"]
            db.commit()

    if d.stop_capture and pj:
        if profile:
            scheduler.remove_capture_job(profile.id)
            profile.enabled = False
        pj.status = "finished" if d.event == "print_finished" else "cancelled"
        pj.finished_at = datetime.now(UTC)
        db.commit()

    should_generate = d.generate
    if d.event == "print_finished" and not cfg.get("generate_on_finish", True):
        should_generate = False
    if should_generate and pj and profile:
        await generation_queue.enqueue_generation(
            profile_id=profile.id,
            period_type="custom",
            period_start=pj.started_at,
            period_end=datetime.now(UTC),
            fps_mode="target_duration",
            fps=cfg["clip_fps"],
            render_target_seconds=cfg["clip_seconds"],
            format="mp4",
            timestamp_overlay=cfg.get("timestamp_overlay", True),
            logo_overlay=cfg.get("logo_overlay", False),
            deflicker=cfg.get("deflicker", "medium"),
            ha_overlay=bool(profile.ha_sensors),
            name=pj.gcode_name or None,
            print_job_id=pj.id,
        )

    if d.event:
        title, level = _EVENT_META.get(d.event, (d.event, "info"))
        name = (pj.gcode_name if pj and pj.gcode_name else None) or "print"
        await events.emit(d.event, title, f"{title}: {name}", level=level)

    return d


async def poll_printer() -> None:
    """Scheduled job: poll PrusaLink and reconcile the print lifecycle."""
    db = SessionLocal()
    try:
        cfg = get_config(db)
        if not cfg or not cfg.get("enabled", True) or not cfg.get("stream_id"):
            return
        status = await get_status(cfg["base_url"], cfg["username"], cfg["password"])
        if not status or not status.get("state"):
            return
        await _reconcile(db, cfg, status)
    except Exception:
        logger.exception("PrusaLink poll failed")
    finally:
        db.rollback()
        db.close()
