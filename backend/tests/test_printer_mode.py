"""Printer mode: the chain for a camera the printer films.

The generic chain treats a printer camera's managed plan as a user plan, so
between prints it reported "every capture plan on this camera is disabled" —
a failure, for a camera that is simply waiting. These pin the replacement.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Capture, PrintJob, Profile, Setting, Stream
from app.services.diagnostics import build_diagnostics


def _camera(db, name="Printer"):
    stream = Stream(
        name=name, url="", source_type="rtsp", enabled=True,
        health_status="healthy", consecutive_failures=0,
        last_checked_at=datetime.now(UTC),
    )
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream


def _bind_printer(db, stream_id, **overrides):
    cfg = {"stream_id": stream_id, "enabled": True, "generate_on_finish": True}
    cfg.update(overrides)
    db.add(Setting(key="prusalink_base_url", value="http://printer.local"))
    db.add(Setting(key="prusalink_config", value=json.dumps(cfg)))
    db.commit()


def _managed_plan(db, stream, interval=10):
    profile = Profile(
        stream_id=stream.id, name="3D Print (auto)", interval_seconds=interval,
        enabled=False, managed_by="prusalink",
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _print(db, stream, status="printing", name="One Ring.bgcode", started=None):
    job = PrintJob(
        stream_id=stream.id, gcode_name=name, status=status,
        started_at=started or datetime.now(UTC) - timedelta(minutes=12),
    )
    db.add(job)
    db.commit()
    return job


@pytest.fixture
def connected(monkeypatch):
    from app.services import health_status
    monkeypatch.setattr(health_status, "peek", lambda key: True)


def _states(result):
    return {c["key"]: c["state"] for c in result["checks"]}


# --- the bug this replaces -------------------------------------------------


def test_between_prints_is_idle_not_a_failure(db, connected):
    """The whole point: waiting for a print is not a broken camera."""
    stream = _camera(db)
    _bind_printer(db, stream.id)
    _managed_plan(db, stream)

    result = build_diagnostics(stream, db)

    assert result["status"] == "idle"
    assert result["summary"] == "Waiting for the next print to start."
    # And specifically not the old message.
    assert "capture plan" not in result["summary"]


def test_a_managed_plan_is_never_reported_as_a_user_plan(db, connected):
    """The contradiction: /profiles filtered it out while the diagnostic
    counted it. Printer mode must not mention plans at all."""
    stream = _camera(db)
    _bind_printer(db, stream.id)
    _managed_plan(db, stream)

    assert "plan" not in _states(build_diagnostics(stream, db))


# --- the printer chain -----------------------------------------------------


def test_integration_switched_off(db):
    stream = _camera(db)
    _bind_printer(db, stream.id, enabled=False)

    result = build_diagnostics(stream, db)

    assert result["status"] == "idle"
    assert "switched off" in result["summary"]
    assert result["action"] == "open_printer_settings"


def test_printer_unreachable_is_a_failure(db, monkeypatch):
    from app.services import health_status
    monkeypatch.setattr(health_status, "peek", lambda key: False)
    stream = _camera(db)
    _bind_printer(db, stream.id)

    result = build_diagnostics(stream, db)

    assert result["status"] == "fail"
    assert "Can't reach the printer" in result["summary"]
    assert result["action"] == "open_printer_settings"


def test_unknown_reachability_is_not_reported_as_unreachable(db, monkeypatch):
    """A cold cache means "not checked", which must not read as a fault."""
    from app.services import health_status
    monkeypatch.setattr(health_status, "peek", lambda key: None)
    stream = _camera(db)
    _bind_printer(db, stream.id)

    result = build_diagnostics(stream, db)

    assert result["status"] != "fail"
    assert _states(result)["printer"] == "warn"


def test_a_running_print_names_it(db, connected):
    stream = _camera(db)
    _bind_printer(db, stream.id)
    plan = _managed_plan(db, stream)
    _print(db, stream)
    now = datetime.now(UTC)
    db.add(Capture(profile_id=plan.id, file_path="/tmp/a.jpg", file_size=1,
                   captured_at=now - timedelta(seconds=5)))
    db.commit()

    result = build_diagnostics(stream, db, now=now)

    assert result["status"] == "ok"
    assert "One Ring.bgcode" in result["summary"]
    assert "12 min ago" in result["summary"]


def test_a_running_print_with_stalled_frames_is_a_failure(db, connected):
    stream = _camera(db)
    _bind_printer(db, stream.id)
    plan = _managed_plan(db, stream, interval=10)
    _print(db, stream)
    now = datetime.now(UTC)
    db.add(Capture(profile_id=plan.id, file_path="/tmp/a.jpg", file_size=1,
                   captured_at=now - timedelta(minutes=8)))
    db.commit()

    result = build_diagnostics(stream, db, now=now)

    assert result["status"] == "fail"
    assert "last frame was" in result["summary"]


def test_auto_render_off_is_said_out_loud(db, connected):
    stream = _camera(db)
    _bind_printer(db, stream.id, generate_on_finish=False)
    plan = _managed_plan(db, stream)
    _print(db, stream)
    now = datetime.now(UTC)
    db.add(Capture(profile_id=plan.id, file_path="/tmp/a.jpg", file_size=1,
                   captured_at=now - timedelta(seconds=5)))
    db.commit()

    result = build_diagnostics(stream, db, now=now)

    assert result["status"] == "idle"
    assert "not rendered automatically" in result["summary"]


def test_a_finished_print_does_not_count_as_running(db, connected):
    stream = _camera(db)
    _bind_printer(db, stream.id)
    _managed_plan(db, stream)
    _print(db, stream, status="finished")

    assert build_diagnostics(stream, db)["summary"] == "Waiting for the next print to start."


# --- the generic chain is untouched for everyone else ----------------------


def test_an_ordinary_camera_still_uses_the_generic_chain(db):
    stream = _camera(db, name="Front")
    other = _camera(db, name="Printer")
    _bind_printer(db, other.id)

    result = build_diagnostics(stream, db)

    assert "no capture plan" in result["summary"]
    assert result["action"] == "add_plan"


def test_camera_and_source_faults_still_come_first(db):
    """Printer mode starts after the shared links, not before them."""
    stream = _camera(db)
    stream.enabled = False
    db.commit()
    _bind_printer(db, stream.id)

    result = build_diagnostics(stream, db)

    assert result["action"] == "enable_camera"
