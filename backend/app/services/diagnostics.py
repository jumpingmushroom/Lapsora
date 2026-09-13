"""Walk a camera's capture chain and name the first broken link.

Nothing captures until a camera has a source that answers, an enabled capture
plan, a scheduler job, and a moment inside that plan's active window. Nothing
renders until a schedule exists. Each of those was knowable only by opening a
different page and knowing what to look for.

The window check calls `capture._is_within_active_window` — the same function
the capture job gates on — rather than reimplementing the rule. A diagnostic
that disagrees with the thing it describes is worse than none.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import func

from app.models import Capture, Profile, Stream, TimelapseSchedule

logger = logging.getLogger(__name__)

# Matches the capture-gap alerting threshold, so the camera page and the
# notification never disagree about whether frames are late.
GAP_MULTIPLIER = 3


def _as_utc(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes for values stored as UTC-aware."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _humanise(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def _window_description(profile: Profile) -> str:
    if profile.capture_mode == "manual" and profile.active_start_time:
        return f"captures {profile.active_start_time}–{profile.active_end_time}"
    if profile.capture_mode == "sun":
        events = [e for e in (profile.sun_events or "").split(",") if e]
        pretty = ", ".join(e.replace("_", " ") for e in events) or "sun windows"
        return f"captures during {pretty}"
    return "captures continuously"


def _check(key: str, state: str, label: str, detail: str = "") -> dict:
    return {"key": key, "state": state, "label": label, "detail": detail}


def build_diagnostics(stream: Stream, db, now: datetime | None = None) -> dict:
    """Return the camera's capture chain, worst link first.

    `state` is one of ok / warn / fail / idle. `summary` is the sentence the
    camera page leads with: the first thing actually stopping this camera, or
    confirmation that it is working.
    """
    now = now or datetime.now(UTC)
    checks: list[dict] = []

    # --- link 1: the camera itself ---
    if not stream.enabled:
        checks.append(_check("camera", "fail", "Camera is disabled", "Enable it to resume capturing."))
        return _assemble(checks, "Nothing is capturing: this camera is disabled.")
    checks.append(_check("camera", "ok", "Camera is enabled"))

    # --- link 2: the source ---
    if stream.health_status == "unhealthy":
        checked = (
            _humanise((now - _as_utc(stream.last_checked_at)).total_seconds())
            if stream.last_checked_at
            else "never checked"
        )
        fails = stream.consecutive_failures
        checks.append(
            _check(
                "source",
                "fail",
                "Source is unreachable",
                f"{fails} consecutive failure{'s' if fails != 1 else ''}, last checked {checked}.",
            )
        )
        return _assemble(
            checks,
            f"Nothing is capturing: the source is unreachable "
            f"({fails} consecutive failure{'s' if fails != 1 else ''}).",
        )
    if stream.health_status == "healthy":
        checks.append(_check("source", "ok", "Source is reachable"))
    else:
        checks.append(_check("source", "warn", "Source has not been checked yet"))

    # --- link 3: a capture plan exists ---
    profiles = db.query(Profile).filter(Profile.stream_id == stream.id).all()

    if not profiles:
        checks.append(
            _check("plan", "fail", "No capture plan", "A camera captures nothing until it has one.")
        )
        return _assemble(checks, "Nothing is capturing: this camera has no capture plan yet.")

    active = [p for p in profiles if p.enabled and not p.auto_disabled]
    auto_off = [p for p in profiles if p.auto_disabled]

    if not active:
        if auto_off:
            names = ", ".join(p.name for p in auto_off)
            checks.append(
                _check(
                    "plan",
                    "fail",
                    "Capture plans were disabled automatically",
                    f"{names} — switched off after repeated source failures.",
                )
            )
            return _assemble(
                checks,
                "Nothing is capturing: the capture plans were disabled automatically "
                "after repeated source failures.",
            )
        checks.append(
            _check("plan", "fail", "All capture plans are disabled", f"{len(profiles)} plan(s), none enabled.")
        )
        return _assemble(checks, "Nothing is capturing: every capture plan on this camera is disabled.")

    checks.append(
        _check(
            "plan",
            "ok",
            f"{len(active)} capture plan{'s' if len(active) != 1 else ''} enabled",
            f"{len(auto_off)} disabled automatically." if auto_off else "",
        )
    )

    # --- link 4: the scheduler is actually running them ---
    from app.services.scheduler import scheduler

    # A stopped scheduler and a missing job look identical from get_job, but
    # they are different faults with different fixes, so separate them.
    if not getattr(scheduler, "running", False):
        checks.append(
            _check(
                "scheduler",
                "fail",
                "Scheduler is not running",
                "No capture job can fire while it is stopped.",
            )
        )
        return _assemble(
            checks,
            "Nothing is capturing: the scheduler is not running. "
            "Restarting Lapsora should start it.",
        )

    unscheduled = []
    for profile in active:
        try:
            if scheduler.get_job(f"capture_{profile.id}") is None:
                unscheduled.append(profile)
        except Exception:
            logger.warning("Could not inspect capture job for profile %d", profile.id)
            break

    if unscheduled:
        names = ", ".join(p.name for p in unscheduled)
        checks.append(
            _check(
                "scheduler",
                "fail",
                "Capture job is not registered",
                f"{names} — restarting Lapsora re-registers it.",
            )
        )
        return _assemble(
            checks,
            f"Nothing is capturing: the capture job for {names} is not registered. "
            "Restarting Lapsora should restore it.",
        )
    checks.append(_check("scheduler", "ok", "Capture jobs are scheduled"))

    # --- link 5: are we inside an active window right now? ---
    from app.services.capture import _is_within_active_window

    in_window = []
    for profile in active:
        try:
            if _is_within_active_window(profile, db, now):
                in_window.append(profile)
        except Exception:
            logger.warning("Active-window check failed for profile %d", profile.id)
            in_window.append(profile)  # match capture.py, which allows on error

    if not in_window:
        first = active[0]
        local_now = now.astimezone().strftime("%H:%M")
        checks.append(
            _check(
                "window",
                "idle",
                "Outside the active window",
                f"{first.name} {_window_description(first)}.",
            )
        )
        return _assemble(
            checks,
            f"Waiting: {first.name} {_window_description(first)}, and it is {local_now}.",
            status="idle",
        )
    checks.append(_check("window", "ok", "Inside the active window"))

    # --- link 6: are frames actually landing? ---
    last_by_profile = dict(
        db.query(Capture.profile_id, func.max(Capture.captured_at))
        .filter(Capture.profile_id.in_([p.id for p in in_window]))
        .group_by(Capture.profile_id)
        .all()
    )

    stale: list[tuple[Profile, float | None]] = []
    newest: float | None = None
    for profile in in_window:
        last = last_by_profile.get(profile.id)
        if last is None:
            # A plan younger than its own first interval has not missed anything.
            age = (now - _as_utc(profile.created_at)).total_seconds()
            if age > profile.interval_seconds * GAP_MULTIPLIER:
                stale.append((profile, None))
            continue
        gap = (now - _as_utc(last)).total_seconds()
        newest = gap if newest is None else min(newest, gap)
        if gap > profile.interval_seconds * GAP_MULTIPLIER:
            stale.append((profile, gap))

    if stale:
        profile, gap = stale[0]
        every = f"every {profile.interval_seconds}s"
        if gap is None:
            detail = f"{profile.name} has never captured a frame."
            summary = f"Not capturing: {profile.name} has never produced a frame."
        else:
            detail = f"{profile.name} should capture {every}; last frame {_humanise(gap)}."
            summary = (
                f"Not capturing: {profile.name} should capture {every}, "
                f"but the last frame was {_humanise(gap)}."
            )
        checks.append(_check("frames", "fail", "Frames are overdue", detail))
        return _assemble(checks, summary)

    checks.append(
        _check(
            "frames",
            "ok",
            "Frames are landing",
            f"Last frame {_humanise(newest)}." if newest is not None else "",
        )
    )

    # --- link 7: rendering. Not a failure, but worth saying out loud. ---
    schedule_count = (
        db.query(func.count(TimelapseSchedule.id))
        .filter(
            TimelapseSchedule.profile_id.in_([p.id for p in active]),
            TimelapseSchedule.enabled.is_(True),
        )
        .scalar()
    )
    if schedule_count:
        checks.append(
            _check("render", "ok", f"{schedule_count} render schedule{'s' if schedule_count != 1 else ''}")
        )
        summary = "Capturing normally."
        if newest is not None:
            summary = f"Capturing normally — last frame {_humanise(newest)}."
        return _assemble(checks, summary, status="ok")

    checks.append(
        _check(
            "render",
            "idle",
            "No render schedule",
            "Frames are being kept, but no timelapse is produced automatically.",
        )
    )
    tail = f" — last frame {_humanise(newest)}" if newest is not None else ""
    return _assemble(
        checks,
        f"Capturing{tail}, but nothing renders automatically: there is no render schedule.",
        status="idle",
    )


def _assemble(checks: list[dict], summary: str, status: str | None = None) -> dict:
    if status is None:
        status = "fail" if any(c["state"] == "fail" for c in checks) else "ok"
    return {"status": status, "summary": summary, "checks": checks}
