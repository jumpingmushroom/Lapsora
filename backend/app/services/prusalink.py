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
    """Extract the bits we care about from a PrusaLink /api/v1/status response.

    Note: real firmware does NOT put a `file` object here — Prusa's OpenAPI
    `StatusJob` is only id/progress/time_remaining/time_printing, so
    `gcode_name` is normally None and the caller must use `get_job`. The `file`
    lookup below is kept as a tolerant fallback, not an expected path."""
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


def parse_job(data: dict) -> dict:
    """Extract the file metadata from a PrusaLink /api/v1/job response.

    This is the only endpoint that carries the printed filename; /api/v1/status
    does not (see `parse_status`)."""
    job = data or {}
    file_info = job.get("file") or {}
    return {
        "job_id": job.get("id"),
        "gcode_name": file_info.get("display_name") or file_info.get("name"),
    }


async def get_job(base_url: str, username: str, password: str) -> dict | None:
    """Fetch the current job's file metadata, or None if there is no job.

    PrusaLink answers 204 (no body) when nothing is printing, so a non-200 is a
    normal idle state rather than an error worth surfacing."""
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=STATUS_TIMEOUT) as client:
            resp = await client.get(f"{base}/api/v1/job", auth=_auth(username, password))
        if resp.status_code != 200:
            return None
        return parse_job(resp.json())
    except Exception as exc:
        logger.debug("PrusaLink job fetch failed for %s: %s", base, exc)
        return None


# --- config + persisted state ----------------------------------------------


def _get_setting(db, key: str) -> str | None:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


_password_error_logged = False


def get_config(db) -> dict | None:
    """Return the merged PrusaLink config (incl. decrypted password), or None if
    unset — or if a stored password can't be decrypted (a corrupted-key state).

    Returning None on decrypt failure treats the integration as unconfigured, so
    the poller stops rather than looping forever with an empty password that
    fails digest auth on every poll, and the settings badge shows disconnected."""
    global _password_error_logged
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
    if pw:
        try:
            cfg["password"] = decrypt(pw)
            _password_error_logged = False
        except Exception:
            # Log once (the poll runs every ~10s) until it decrypts again.
            if not _password_error_logged:
                logger.warning(
                    "PrusaLink password could not be decrypted (SECRET_KEY "
                    "changed?); treating the integration as unconfigured until "
                    "the password is re-entered"
                )
                _password_error_logged = True
            return None
    else:
        cfg["password"] = ""
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

    # Job-id change while still 'printing': the previous print finished and a new
    # one began within a single poll interval (we never observed a non-printing
    # state between them). Close the old print (finish + generate) as if we had
    # polled FINISHED, then start the new one from idle — otherwise both prints
    # merge into one PrintJob/timelapse under the first print's name.
    incoming_job_id = status.get("job_id")
    if (
        pj is not None
        and state == "printing"
        and incoming_job_id is not None
        and pj.prusalink_job_id is not None
        and incoming_job_id != pj.prusalink_job_id
    ):
        await _reconcile(db, cfg, {**status, "state": "FINISHED"})
        return await _reconcile(db, cfg, status)

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
        profile.auto_disabled = False
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
            # Clear any stale auto-disable marker left by a mid-print stream
            # flap so health recovery can't re-enable this profile once the
            # print is over (it would then capture forever with no print).
            profile.auto_disabled = False
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


def _needs_gcode_name(db, status: dict) -> bool:
    """Whether this poll should spend an extra request on /api/v1/job.

    Only while a print is live (the endpoint 204s otherwise) and only until we
    have a name — so this costs about one request per print, not one per poll."""
    if status.get("gcode_name"):
        return False
    if normalize_state(status.get("state")) not in ("printing", "paused"):
        return False
    pj = _open_print_job(db)
    return pj is None or not pj.gcode_name


# How long a printer may stay unreachable mid-print before we close the open
# print (as cancelled) so the managed capture profile doesn't run forever.
UNREACHABLE_GRACE_SECONDS = 900

# In-memory: open print_job id -> first time we polled it and got no status.
_unreachable_since: dict[int, datetime] = {}


async def _handle_unreachable(db) -> None:
    """A poll returned no status. If a print is open and the printer has been
    unreachable past the grace period, close it (cancelled) and stop capturing —
    otherwise a printer powered off mid-print leaves the print and the managed
    capture profile running indefinitely."""
    pj = _open_print_job(db)
    if not pj:
        _unreachable_since.clear()
        return
    now = datetime.now(UTC)
    first = _unreachable_since.setdefault(pj.id, now)
    if (now - first).total_seconds() < UNREACHABLE_GRACE_SECONDS:
        return
    profile = db.query(Profile).filter(Profile.managed_by == "prusalink").first()
    if profile:
        scheduler.remove_capture_job(profile.id)
        profile.enabled = False
        profile.auto_disabled = False
    pj.status = "cancelled"
    pj.finished_at = now
    db.commit()
    _unreachable_since.pop(pj.id, None)
    await events.emit(
        "print_failed",
        "Print stopped",
        f"Print stopped: printer unreachable for over "
        f"{UNREACHABLE_GRACE_SECONDS // 60} minutes.",
        level="warning",
    )


async def poll_printer() -> None:
    """Scheduled job: poll PrusaLink and reconcile the print lifecycle."""
    db = SessionLocal()
    try:
        cfg = get_config(db)
        if not cfg or not cfg.get("enabled", True) or not cfg.get("stream_id"):
            return
        status = await get_status(cfg["base_url"], cfg["username"], cfg["password"])

        # The filename lives only on /api/v1/job. Fetch it here, before the
        # staleness checkpoint below, so all network awaits stay on one side of
        # it and there remains a single point where we re-read config.
        if status and status.get("state") and _needs_gcode_name(db, status):
            job = await get_job(cfg["base_url"], cfg["username"], cfg["password"])
            if job and job.get("gcode_name"):
                status["gcode_name"] = job["gcode_name"]

        # Re-read config after the network await: a PUT that disabled the
        # integration (and removed this poll job) may have committed while we
        # waited on get_status. Drop the read snapshot so we observe the commit,
        # and bail before mutating state on stale config — otherwise we would
        # recreate a PrintJob / re-enable the managed profile that nothing will
        # ever close.
        db.rollback()
        cfg = get_config(db)
        if not cfg or not cfg.get("enabled", True) or not cfg.get("stream_id"):
            return

        if not status or not status.get("state"):
            await _handle_unreachable(db)
            return
        _unreachable_since.clear()
        await _reconcile(db, cfg, status)
    except Exception:
        logger.exception("PrusaLink poll failed")
    finally:
        db.rollback()
        db.close()
