"""The capture-chain diagnostic.

One assertion runs through all of these: the summary must name the *first*
thing actually stopping this camera. A diagnostic that reports the second
problem, or that disagrees with what the capture job will really do, sends
someone to fix the wrong thing.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Capture, Profile, Stream, TimelapseSchedule
from app.services.diagnostics import build_diagnostics


def _camera(db, **kw):
    stream = Stream(
        name=kw.pop("name", "cam"),
        url="",
        source_type="rtsp",
        enabled=kw.pop("enabled", True),
        health_status=kw.pop("health_status", "healthy"),
        consecutive_failures=kw.pop("consecutive_failures", 0),
        last_checked_at=kw.pop("last_checked_at", datetime.now(UTC)),
        **kw,
    )
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream


def _plan(db, stream, **kw):
    created = kw.pop("created_at", datetime.now(UTC) - timedelta(days=1))
    profile = Profile(
        stream_id=stream.id,
        name=kw.pop("name", "plan"),
        interval_seconds=kw.pop("interval_seconds", 60),
        created_at=created,
        **kw,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _frame(db, profile, when):
    db.add(Capture(profile_id=profile.id, file_path="/tmp/x.jpg", file_size=1, captured_at=when))
    db.commit()


def _states(result):
    return {c["key"]: c["state"] for c in result["checks"]}


@pytest.fixture
def running_scheduler(monkeypatch):
    """A scheduler that is up with every capture job registered.

    Most of these tests are about links further down the chain, so they need
    the scheduler link to pass. The two scheduler faults get their own tests.
    """

    class _Stub:
        running = True

        def get_job(self, job_id):
            return object()

    from app.services import scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "scheduler", _Stub())


@pytest.fixture
def in_window(monkeypatch):
    from app.services import capture

    monkeypatch.setattr(capture, "_is_within_active_window", lambda p, d, n: True)


def test_disabled_camera_is_reported_before_anything_else(db):
    """A disabled camera must not be described as 'no capture plan'."""
    stream = _camera(db, enabled=False)

    result = build_diagnostics(stream, db)

    assert result["status"] == "fail"
    assert "disabled" in result["summary"]
    # The walk stops at the first break rather than listing every later one.
    assert list(_states(result)) == ["camera"]


def test_unreachable_source_beats_a_missing_plan(db):
    stream = _camera(db, health_status="unhealthy", consecutive_failures=4)
    # No plan either — the source is still the thing to fix first.

    result = build_diagnostics(stream, db)

    assert result["status"] == "fail"
    assert "unreachable" in result["summary"]
    assert "4 consecutive failures" in result["summary"]


def test_missing_capture_plan_is_named_plainly(db):
    stream = _camera(db)

    result = build_diagnostics(stream, db)

    assert result["status"] == "fail"
    assert "no capture plan" in result["summary"]


def test_all_plans_disabled(db):
    stream = _camera(db)
    _plan(db, stream, enabled=False)

    result = build_diagnostics(stream, db)

    assert result["status"] == "fail"
    assert "disabled" in result["summary"]


def test_auto_disabled_plans_say_why(db):
    """'Disabled' and 'disabled itself after failures' need different fixes."""
    stream = _camera(db)
    _plan(db, stream, enabled=True, auto_disabled=True)

    result = build_diagnostics(stream, db)

    assert result["status"] == "fail"
    assert "automatically" in result["summary"]
    assert "repeated source failures" in result["summary"]


def test_outside_the_active_window_is_idle_not_broken(db, monkeypatch, running_scheduler):
    """Waiting for 06:00 is not a fault, and must not read as one."""
    stream = _camera(db)
    _plan(db, stream, name="Daylight", capture_mode="manual",
          active_start_time="06:00", active_end_time="20:00")

    from app.services import capture
    monkeypatch.setattr(capture, "_is_within_active_window", lambda p, d, n: False)

    result = build_diagnostics(stream, db)

    assert result["status"] == "idle"
    assert "Waiting" in result["summary"]
    assert "Daylight" in result["summary"]
    assert "06:00–20:00" in result["summary"]


def test_overdue_frames_quote_the_interval_and_the_gap(db, running_scheduler, in_window):
    stream = _camera(db)
    plan = _plan(db, stream, name="Yard", interval_seconds=60)
    now = datetime.now(UTC)
    _frame(db, plan, now - timedelta(hours=2))

    result = build_diagnostics(stream, db, now=now)

    assert result["status"] == "fail"
    assert "Yard" in result["summary"]
    assert "every 60s" in result["summary"]
    assert "2 hours ago" in result["summary"]


def test_a_brand_new_plan_is_not_called_overdue(db, running_scheduler, in_window):
    """A plan younger than its own first interval has missed nothing yet."""
    stream = _camera(db)
    now = datetime.now(UTC)
    _plan(db, stream, interval_seconds=300, created_at=now - timedelta(seconds=30))

    result = build_diagnostics(stream, db, now=now)

    assert result["status"] != "fail"


def test_an_old_plan_with_no_frames_at_all_is_reported(db, running_scheduler, in_window):
    stream = _camera(db)
    now = datetime.now(UTC)
    _plan(db, stream, name="Yard", interval_seconds=60, created_at=now - timedelta(days=1))

    result = build_diagnostics(stream, db, now=now)

    assert result["status"] == "fail"
    assert "never" in result["summary"]


def test_capturing_without_a_schedule_is_idle_and_says_so(db, running_scheduler, in_window):
    stream = _camera(db)
    plan = _plan(db, stream, interval_seconds=60)
    now = datetime.now(UTC)
    _frame(db, plan, now - timedelta(seconds=10))

    result = build_diagnostics(stream, db, now=now)

    assert result["status"] == "idle"
    assert "no render schedule" in result["summary"]
    assert _states(result)["frames"] == "ok"


def test_a_fully_working_camera_says_so(db, running_scheduler, in_window):
    stream = _camera(db)
    plan = _plan(db, stream, interval_seconds=60)
    now = datetime.now(UTC)
    _frame(db, plan, now - timedelta(seconds=10))
    db.add(
        TimelapseSchedule(profile_id=plan.id, cron_expression="5 0 * * *", enabled=True)
    )
    db.commit()

    result = build_diagnostics(stream, db, now=now)

    assert result["status"] == "ok"
    assert result["summary"].startswith("Capturing normally")
    assert all(c["state"] == "ok" for c in result["checks"])


def test_a_disabled_schedule_does_not_count_as_rendering(db, running_scheduler, in_window):
    stream = _camera(db)
    plan = _plan(db, stream, interval_seconds=60)
    now = datetime.now(UTC)
    _frame(db, plan, now - timedelta(seconds=10))
    db.add(
        TimelapseSchedule(profile_id=plan.id, cron_expression="5 0 * * *", enabled=False)
    )
    db.commit()

    result = build_diagnostics(stream, db, now=now)

    assert result["status"] == "idle"
    assert "no render schedule" in result["summary"]


def test_window_check_delegates_to_the_capture_gate(db, monkeypatch, running_scheduler):
    """The rule must come from the function the capture job itself uses, not a
    copy of it that can drift."""
    stream = _camera(db)
    _plan(db, stream)
    calls = []

    from app.services import capture
    real = capture._is_within_active_window

    def spy(profile, session, when):
        calls.append(profile.id)
        return real(profile, session, when)

    monkeypatch.setattr(capture, "_is_within_active_window", spy)
    build_diagnostics(stream, db)

    assert calls, "diagnostics must consult capture._is_within_active_window"


@pytest.mark.parametrize("health", ["unknown", "healthy"])
def test_unchecked_source_does_not_block_the_walk(db, health, running_scheduler, in_window):
    stream = _camera(db, health_status=health)
    plan = _plan(db, stream, interval_seconds=60)
    now = datetime.now(UTC)
    _frame(db, plan, now - timedelta(seconds=5))

    result = build_diagnostics(stream, db, now=now)

    assert "frames" in _states(result)


def test_endpoint_returns_the_chain(client, db):
    stream = _camera(db)

    resp = client.get(f"/api/streams/{stream.id}/diagnostics")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "fail"
    assert body["checks"][0]["key"] == "camera"


def test_endpoint_404s_for_an_unknown_camera(client):
    assert client.get("/api/streams/9999/diagnostics").status_code == 404


def test_a_stopped_scheduler_is_named_as_the_fault(db, monkeypatch):
    """A stopped scheduler and a missing job look identical from get_job, but
    need different fixes, so they must not be reported as the same thing."""
    stream = _camera(db)
    _plan(db, stream)

    class _Stopped:
        running = False

        def get_job(self, job_id):
            return None

    from app.services import scheduler as scheduler_module
    monkeypatch.setattr(scheduler_module, "scheduler", _Stopped())

    result = build_diagnostics(stream, db)

    assert result["status"] == "fail"
    assert "scheduler is not running" in result["summary"]
    assert _states(result)["scheduler"] == "fail"


def test_a_missing_capture_job_names_the_plan(db, monkeypatch):
    stream = _camera(db)
    _plan(db, stream, name="Yard")

    class _NoJobs:
        running = True

        def get_job(self, job_id):
            return None

    from app.services import scheduler as scheduler_module
    monkeypatch.setattr(scheduler_module, "scheduler", _NoJobs())

    result = build_diagnostics(stream, db)

    assert result["status"] == "fail"
    assert "Yard" in result["summary"]
    assert "not registered" in result["summary"]


# --- the one-click fix each gap implies -------------------------------------


def test_missing_plan_offers_adding_one(db):
    stream = _camera(db)
    assert build_diagnostics(stream, db)["action"] == "add_plan"


def test_disabled_camera_offers_enabling_it(db):
    stream = _camera(db, enabled=False)
    assert build_diagnostics(stream, db)["action"] == "enable_camera"


def test_capturing_without_a_schedule_offers_adding_one(db, running_scheduler, in_window):
    stream = _camera(db)
    plan = _plan(db, stream, interval_seconds=60)
    now = datetime.now(UTC)
    _frame(db, plan, now - timedelta(seconds=10))

    assert build_diagnostics(stream, db, now=now)["action"] == "add_schedule"


def test_a_working_camera_offers_nothing(db, running_scheduler, in_window):
    stream = _camera(db)
    plan = _plan(db, stream, interval_seconds=60)
    now = datetime.now(UTC)
    _frame(db, plan, now - timedelta(seconds=10))
    db.add(TimelapseSchedule(profile_id=plan.id, cron_expression="5 0 * * *", enabled=True))
    db.commit()

    assert build_diagnostics(stream, db, now=now)["action"] is None


def test_faults_with_no_one_click_fix_offer_nothing(db, running_scheduler, in_window):
    """An unreachable source needs a human, not a button."""
    stream = _camera(db, health_status="unhealthy", consecutive_failures=3)
    _plan(db, stream)

    assert build_diagnostics(stream, db)["action"] is None
