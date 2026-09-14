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

from app.models import Capture, PrintJob, Profile, Stream, TimelapseSchedule

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
        return _assemble(
            checks,
            "Nothing is capturing: this camera is disabled.",
            action="enable_camera",
        )
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

    # --- printer-bound cameras answer a different chain from here on ---
    from app.services import prusalink

    if prusalink.bound_stream_id(db) == stream.id:
        return _printer_diagnostics(stream, db, now, checks)

    # --- link 3: a capture plan exists ---
    profiles = db.query(Profile).filter(Profile.stream_id == stream.id).all()

    if not profiles:
        checks.append(
            _check("plan", "fail", "No capture plan", "A camera captures nothing until it has one.")
        )
        return _assemble(
            checks,
            "Nothing is capturing: this camera has no capture plan yet.",
            action="add_plan",
        )

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
        # A schedule whose boundary lands inside the capture window renders the
        # end of one session and the start of the next. Everything else here
        # reports green for it — the frames are all present and correct — so it
        # is only findable by watching a video.
        split = _split_schedules(active, db)
        if split:
            name, when = split[0]
            checks.append(
                _check(
                    "render",
                    "warn",
                    "A schedule splits the capture window",
                    f"{name} starts at {when}, mid-session.",
                )
            )
            return _assemble(
                checks,
                f"Renders are splitting each session in two: {name} starts at {when}, "
                "in the middle of the capture window.",
                status="idle",
                action="fix_schedule_boundary",
            )

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
        action="add_schedule",
    )


def _split_schedules(profiles: list[Profile], db) -> list[tuple[str, str]]:
    """(schedule name, fire time) for schedules whose boundary cuts a window.

    Only reports the ones that can actually be fixed: a plan capturing round
    the clock has no clean boundary, so flagging it would be nagging about
    something the user cannot resolve.
    """
    from app.services import render_boundary

    found: list[tuple[str, str]] = []
    for profile in profiles:
        if render_boundary.captures_continuously(profile, db):
            continue
        schedules = (
            db.query(TimelapseSchedule)
            .filter(
                TimelapseSchedule.profile_id == profile.id,
                TimelapseSchedule.enabled.is_(True),
            )
            .all()
        )
        for schedule in schedules:
            parsed = render_boundary.parse_cron_time(schedule.cron_expression)
            if parsed is None:
                continue
            hour, minute = parsed
            if render_boundary.boundary_splits_window(profile, db, hour, minute):
                found.append((schedule.name or "A render schedule", f"{hour:02d}:{minute:02d}"))
    return found


def _printer_diagnostics(
    stream: Stream, db, now: datetime, checks: list[dict]
) -> dict:
    """The chain for a camera the printer films.

    A print is an external event, not a schedule, so the questions after
    "is the source reachable" are different ones: is the integration on, can we
    hear the printer, is it printing, are frames landing. Between prints this
    camera is idle — it is waiting, not broken, and the generic chain calling
    that a failure is what prompted this.
    """
    from app.services import health_status, prusalink

    cfg = prusalink.get_config(db)
    configured = cfg is not None

    if not configured or not cfg.get("enabled", True):
        checks.append(
            _check(
                "printer",
                "idle",
                "Printer integration is off",
                "Prints are not being filmed.",
            )
        )
        return _assemble(
            checks,
            "The printer integration is switched off, so prints aren't being filmed.",
            status="idle",
            action="open_printer_settings",
        )

    # Last known reachability. None means nothing has probed recently, which is
    # not the same as unreachable and must not be reported as a failure.
    reachable = health_status.peek("prusalink")
    if reachable is False:
        checks.append(
            _check(
                "printer",
                "fail",
                "Printer is unreachable",
                "Lapsora won't know when a print starts.",
            )
        )
        return _assemble(
            checks,
            "Can't reach the printer. Lapsora won't know when a print starts.",
            action="open_printer_settings",
        )

    checks.append(
        _check(
            "printer",
            "ok" if reachable else "warn",
            "Printer connected" if reachable else "Printer not checked recently",
        )
    )

    open_print = (
        db.query(PrintJob)
        .filter(PrintJob.stream_id == stream.id, PrintJob.status == "printing")
        .order_by(PrintJob.id.desc())
        .first()
    )

    if open_print is None:
        checks.append(_check("print", "idle", "No print running"))
        return _assemble(
            checks,
            "Waiting for the next print to start.",
            status="idle",
        )

    name = open_print.gcode_name or "an untitled print"
    started = _humanise((now - _as_utc(open_print.started_at)).total_seconds())
    checks.append(_check("print", "ok", f"Filming {name}", f"Started {started}."))

    # A print that is running but producing nothing is the one real failure
    # this chain can report, and the one worth interrupting someone for.
    profile = (
        db.query(Profile)
        .filter(Profile.stream_id == stream.id, Profile.managed_by == "prusalink")
        .first()
    )
    last = None
    if profile:
        last = (
            db.query(func.max(Capture.captured_at))
            .filter(Capture.profile_id == profile.id)
            .scalar()
        )

    if profile and last is not None:
        gap = (now - _as_utc(last)).total_seconds()
        if gap > profile.interval_seconds * GAP_MULTIPLIER:
            checks.append(
                _check("frames", "fail", "Frames are overdue", f"Last frame {_humanise(gap)}.")
            )
            return _assemble(
                checks,
                f"Filming {name}, but the last frame was {_humanise(gap)}.",
            )
        checks.append(_check("frames", "ok", "Frames are landing", f"Last frame {_humanise(gap)}."))
    else:
        checks.append(_check("frames", "warn", "No frames captured yet"))

    summary = f"Filming {name} — started {started}."
    if not cfg.get("generate_on_finish", True):
        checks.append(
            _check("render", "idle", "Auto-render is off", "The print won't be rendered when it finishes.")
        )
        return _assemble(
            checks,
            summary + " Prints are filmed but not rendered automatically.",
            status="idle",
        )

    checks.append(_check("render", "ok", "Renders when the print finishes"))
    return _assemble(checks, summary, status="ok")


def _assemble(
    checks: list[dict],
    summary: str,
    status: str | None = None,
    action: str | None = None,
) -> dict:
    """`action` names the one-click fix, where there is one.

    Naming it here rather than letting the UI match on the summary text keeps
    the two from drifting: a reworded sentence would otherwise silently lose
    its button.
    """
    if status is None:
        status = "fail" if any(c["state"] == "fail" for c in checks) else "ok"
    return {"status": status, "summary": summary, "checks": checks, "action": action}
