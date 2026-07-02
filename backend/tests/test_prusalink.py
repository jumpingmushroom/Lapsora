"""Tests for the PrusaLink print-state reconcile logic.

The poller polls PrusaLink's status on an interval; `decide_transition` is the pure
state machine that turns (were-we-capturing, newly-polled-state) into the side effects
the poller should perform. Keeping it pure makes the transitions testable without a
printer, the scheduler, or the DB.
"""

import pytest

from app.services import prusalink as pl


# --- normalize_state -------------------------------------------------------

def test_normalize_known_states():
    assert pl.normalize_state("PRINTING") == "printing"
    assert pl.normalize_state("PAUSED") == "paused"
    assert pl.normalize_state("FINISHED") == "finished"


def test_normalize_is_case_and_whitespace_tolerant():
    assert pl.normalize_state(" printing ") == "printing"


def test_normalize_unknown_and_terminal_states_collapse_to_other():
    for raw in ("IDLE", "READY", "STOPPED", "ERROR", "ATTENTION", "BUSY", "", None):
        assert pl.normalize_state(raw) == "other"


# --- decide_transition -----------------------------------------------------

def test_idle_to_printing_starts_capture():
    d = pl.decide_transition(active=False, state="printing")
    assert d.capturing is True
    assert d.start_capture is True
    assert d.stop_capture is False
    assert d.generate is False
    assert d.event == "print_started"


def test_printing_to_printing_is_a_noop_continue():
    d = pl.decide_transition(active=True, state="printing")
    assert d.capturing is True
    assert d.start_capture is False
    assert d.stop_capture is False
    assert d.generate is False
    assert d.event is None


def test_printing_to_finished_stops_and_generates():
    d = pl.decide_transition(active=True, state="finished")
    assert d.capturing is False
    assert d.stop_capture is True
    assert d.generate is True
    assert d.event == "print_finished"


def test_printing_to_cancelled_stops_without_generating_by_default():
    d = pl.decide_transition(active=True, state="other")
    assert d.capturing is False
    assert d.stop_capture is True
    assert d.generate is False
    assert d.event == "print_failed"


def test_cancel_can_opt_into_generation():
    d = pl.decide_transition(active=True, state="other", generate_on_cancel=True)
    assert d.generate is True
    assert d.event == "print_failed"


def test_paused_while_active_keeps_capturing():
    d = pl.decide_transition(active=True, state="paused")
    assert d.capturing is True
    assert d.start_capture is False
    assert d.stop_capture is False
    assert d.event is None


def test_paused_while_idle_does_not_start():
    d = pl.decide_transition(active=False, state="paused")
    assert d.capturing is False
    assert d.start_capture is False


def test_unrelated_states_while_idle_are_noops():
    for state in ("finished", "other"):
        d = pl.decide_transition(active=False, state=state)
        assert d.capturing is False
        assert d.start_capture is False
        assert d.stop_capture is False
        assert d.generate is False
        assert d.event is None


# --- parse_status ----------------------------------------------------------

def test_parse_status_extracts_printer_state_and_job():
    data = {"printer": {"state": "PRINTING"}, "job": {"id": 42, "progress": 37}}
    out = pl.parse_status(data)
    assert out["state"] == "PRINTING"
    assert out["job_id"] == 42
    assert out["progress"] == 37


def test_parse_status_tolerates_missing_job():
    out = pl.parse_status({"printer": {"state": "IDLE"}})
    assert out["state"] == "IDLE"
    assert out["job_id"] is None


def test_parse_status_tolerates_empty():
    out = pl.parse_status({})
    assert out["state"] is None


# --- settings roundtrip ----------------------------------------------------

def test_prusalink_settings_roundtrip_masks_password(client):
    resp = client.put("/api/settings/prusalink", json={
        "base_url": "http://prusa.local/", "username": "maker", "password": "pw",
        "profile_id": 7, "poll_interval_seconds": 15, "generate_on_cancel": True,
    })
    assert resp.status_code == 200, resp.text
    got = client.get("/api/settings/prusalink").json()
    assert got["base_url"] == "http://prusa.local"  # trailing slash stripped
    assert got["username"] == "maker"
    assert got["profile_id"] == 7
    assert got["poll_interval_seconds"] == 15
    assert got["generate_on_cancel"] is True
    assert got["connected"] is True
    assert "password" not in got


def test_prusalink_update_without_password_keeps_existing(client):
    client.put("/api/settings/prusalink", json={"base_url": "http://a", "password": "pw1", "profile_id": 1})
    client.put("/api/settings/prusalink", json={"base_url": "http://b", "profile_id": 1})  # no password
    got = client.get("/api/settings/prusalink").json()
    assert got["base_url"] == "http://b"
    assert got["connected"] is True


# --- _reconcile (wiring of a decision to side effects) ---------------------

def _seed_printer_profile(client):
    sid = client.post("/api/streams/", json={"name": "Printer", "url": "rtsp://x"}).json()["id"]
    from unittest.mock import patch
    with patch("app.routers.profiles.scheduler"):
        pid = client.post(f"/api/streams/{sid}/profiles", json={"name": "PrintCam"}).json()["id"]
    return pid


@pytest.mark.asyncio
async def test_reconcile_start_enables_profile_and_adds_job(client, db, monkeypatch):
    from app.models import Profile
    pid = _seed_printer_profile(client)
    db.query(Profile).filter(Profile.id == pid).update({"enabled": False})
    db.commit()

    calls = {}
    monkeypatch.setattr(pl.scheduler, "add_capture_job", lambda profile: calls.setdefault("add", profile.id))

    async def fake_emit(*a, **k):
        calls["event"] = a[0]
    monkeypatch.setattr(pl.events, "emit", fake_emit)

    cfg = {"profile_id": pid, "generate_on_cancel": False, "generate_on_finish": True, "fps": 24, "format": "mp4"}
    d = await pl._reconcile(db, cfg, "PRINTING")

    assert d.start_capture is True
    assert calls["add"] == pid
    assert calls["event"] == "print_started"
    assert db.get(Profile, pid).enabled is True
    # active flag persisted
    from app.models import Setting
    assert db.query(Setting).filter(Setting.key == "prusalink_active").first().value == "true"


@pytest.mark.asyncio
async def test_reconcile_finish_removes_job_and_enqueues_generation(client, db, monkeypatch):
    from app.models import Profile, Setting
    pid = _seed_printer_profile(client)
    # Simulate an in-progress print: active=true with a recorded start.
    # Render config now comes from the bound profile, not cfg; seed render_fps=30
    # so the test's intent (a chosen fps flows through to enqueue) is preserved.
    db.get(Profile, pid).render_fps = 30
    db.add(Setting(key="prusalink_active", value="true"))
    db.add(Setting(key="prusalink_print_started_at", value="2026-06-04 10:00:00"))
    db.commit()

    calls = {}
    monkeypatch.setattr(pl.scheduler, "remove_capture_job", lambda profile_id: calls.setdefault("remove", profile_id))

    async def fake_enqueue(**kwargs):
        calls["gen"] = kwargs
        return {"generation_id": "x", "position": 1}
    monkeypatch.setattr(pl.generation_queue, "enqueue_generation", fake_enqueue)

    async def fake_emit(*a, **k):
        calls["event"] = a[0]
    monkeypatch.setattr(pl.events, "emit", fake_emit)

    cfg = {"profile_id": pid, "generate_on_cancel": False, "generate_on_finish": True, "fps": 30, "format": "mp4"}
    d = await pl._reconcile(db, cfg, "FINISHED")

    assert d.generate is True
    assert calls["remove"] == pid
    assert calls["gen"]["profile_id"] == pid
    assert calls["gen"]["period_type"] == "custom"
    assert calls["gen"]["fps"] == 30
    assert calls["event"] == "print_finished"
    # active flag cleared
    assert db.query(Setting).filter(Setting.key == "prusalink_active").first().value == "false"


@pytest.mark.asyncio
async def test_reconcile_finish_uses_profile_render_config(client, db, monkeypatch):
    from app.models import Profile, Setting
    pid = _seed_printer_profile(client)
    # Give the bound profile a target-duration render config.
    prof = db.get(Profile, pid)
    prof.fps_mode = "target_duration"
    prof.render_target_seconds = 15
    prof.render_fps = 30
    prof.render_format = "mp4"
    db.add(Setting(key="prusalink_active", value="true"))
    db.add(Setting(key="prusalink_print_started_at", value="2026-06-04 10:00:00"))
    db.commit()

    calls = {}
    monkeypatch.setattr(pl.scheduler, "remove_capture_job", lambda profile_id: None)

    async def fake_enqueue(**kwargs):
        calls["gen"] = kwargs
        return {"generation_id": "x", "position": 1}
    monkeypatch.setattr(pl.generation_queue, "enqueue_generation", fake_enqueue)

    async def fake_emit(*a, **k):
        pass
    monkeypatch.setattr(pl.events, "emit", fake_emit)

    # cfg still carries legacy fps/format; the profile config must win.
    cfg = {"profile_id": pid, "generate_on_cancel": False, "generate_on_finish": True, "fps": 24, "format": "mp4"}
    await pl._reconcile(db, cfg, "FINISHED")

    assert calls["gen"]["fps_mode"] == "target_duration"
    assert calls["gen"]["render_target_seconds"] == 15
    assert calls["gen"]["fps"] == 30
    assert calls["gen"]["format"] == "mp4"


@pytest.mark.asyncio
async def test_reconcile_cancel_stops_without_generation(client, db, monkeypatch):
    from app.models import Setting
    pid = _seed_printer_profile(client)
    db.add(Setting(key="prusalink_active", value="true"))
    db.commit()

    calls = {}
    monkeypatch.setattr(pl.scheduler, "remove_capture_job", lambda profile_id: calls.setdefault("remove", profile_id))

    async def fake_enqueue(**kwargs):
        calls["gen"] = kwargs
    monkeypatch.setattr(pl.generation_queue, "enqueue_generation", fake_enqueue)

    async def fake_emit(*a, **k):
        calls["event"] = a[0]
    monkeypatch.setattr(pl.events, "emit", fake_emit)

    cfg = {"profile_id": pid, "generate_on_cancel": False, "generate_on_finish": True, "fps": 24, "format": "mp4"}
    d = await pl._reconcile(db, cfg, "STOPPED")

    assert calls["remove"] == pid
    assert "gen" not in calls
    assert calls["event"] == "print_failed"


# --- compute_interval -------------------------------------------------------

def test_interval_scales_with_estimate():
    # 10h print, 20s x 25fps = 500 frames -> 72s
    assert pl.compute_interval(36000, 20, 25, 10, 2, 120) == 72
    # 25min print -> 3s
    assert pl.compute_interval(1500, 20, 25, 10, 2, 120) == 3

def test_interval_clamps_to_bounds():
    assert pl.compute_interval(60, 20, 25, 10, 2, 120) == 2      # tiny print -> min
    assert pl.compute_interval(1_000_000, 20, 25, 10, 2, 120) == 120  # huge -> max

def test_interval_missing_or_bogus_estimate_uses_default():
    for est in (None, 0, -5):
        assert pl.compute_interval(est, 20, 25, 10, 2, 120) == 10

def test_interval_default_is_also_clamped():
    assert pl.compute_interval(None, 20, 25, 300, 2, 120) == 120


# --- parse_status: job metadata ---------------------------------------------

def test_parse_status_extracts_gcode_name_and_estimate():
    got = pl.parse_status({
        "printer": {"state": "PRINTING"},
        "job": {
            "id": 7, "progress": 12.5,
            "time_printing": 300, "time_remaining": 3300,
            "file": {"name": "benchy~1.gco", "display_name": "benchy.gcode"},
        },
    })
    assert got["gcode_name"] == "benchy.gcode"
    assert got["estimated_seconds"] == 3600.0

def test_parse_status_falls_back_to_file_name():
    got = pl.parse_status({"printer": {}, "job": {"file": {"name": "x.gco"}}})
    assert got["gcode_name"] == "x.gco"

def test_parse_status_no_estimate_when_remaining_missing_or_bogus():
    assert pl.parse_status({"job": {"time_printing": 300}})["estimated_seconds"] is None
    assert pl.parse_status({"job": {"time_remaining": -1}})["estimated_seconds"] is None
    assert pl.parse_status({})["estimated_seconds"] is None
    assert pl.parse_status({})["gcode_name"] is None
