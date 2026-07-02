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

def test_prusalink_settings_roundtrip_masks_password(client, db, monkeypatch):
    from app.services import health_status

    async def _reachable(*a, **kw):
        return True

    monkeypatch.setattr(health_status, "reachable", _reachable)

    s = _stream(db)
    resp = client.put("/api/settings/prusalink", json={
        "base_url": "http://prusa.local/", "username": "maker", "password": "pw",
        "stream_id": s.id, "poll_interval_seconds": 15, "generate_on_cancel": True,
        "enabled": False,
    })
    assert resp.status_code == 200, resp.text
    got = client.get("/api/settings/prusalink").json()
    assert got["base_url"] == "http://prusa.local"  # trailing slash stripped
    assert got["username"] == "maker"
    assert got["stream_id"] == s.id
    assert got["poll_interval_seconds"] == 15
    assert got["generate_on_cancel"] is True
    assert got["connected"] is True
    assert "password" not in got


def test_prusalink_update_without_password_keeps_existing(client, db, monkeypatch):
    from app.services import health_status

    async def _reachable(*a, **kw):
        return True

    monkeypatch.setattr(health_status, "reachable", _reachable)

    s = _stream(db)
    client.put("/api/settings/prusalink", json={"base_url": "http://a", "password": "pw1", "stream_id": s.id, "enabled": False})
    client.put("/api/settings/prusalink", json={"base_url": "http://b", "stream_id": s.id, "enabled": False})  # no password
    got = client.get("/api/settings/prusalink").json()
    assert got["base_url"] == "http://b"
    assert got["connected"] is True


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


# --- ensure_managed_profile --------------------------------------------------

from app.models import Profile, Stream


def _stream(db):
    s = Stream(name="printer-cam", url="rtsp://x")
    db.add(s)
    db.commit()
    return s


def _cfg(**over):
    cfg = pl.DEFAULT_CONFIG.copy()
    cfg.update(over)
    return cfg


def test_ensure_managed_profile_creates_once_and_repoints(db):
    s1, s2 = _stream(db), _stream(db)
    p = pl.ensure_managed_profile(db, _cfg(stream_id=s1.id, quality=85, clip_seconds=30, clip_fps=30))
    assert p.managed_by == "prusalink"
    assert p.name == pl.MANAGED_PROFILE_NAME
    assert p.enabled is False
    assert p.quality == 85
    assert p.fps_mode == "target_duration"
    assert p.render_target_seconds == 30
    assert p.render_fps == 30
    # second call: same row, re-pointed to the other stream
    p2 = pl.ensure_managed_profile(db, _cfg(stream_id=s2.id))
    assert p2.id == p.id
    assert p2.stream_id == s2.id
    assert db.query(Profile).filter(Profile.managed_by == "prusalink").count() == 1


def test_ensure_managed_profile_none_without_stream(db):
    assert pl.ensure_managed_profile(db, _cfg(stream_id=None)) is None


# --- _reconcile lifecycle -----------------------------------------------------

from app.models import PrintJob


@pytest.fixture
def fakes(monkeypatch):
    """Stub the scheduler + generation queue; capture calls."""
    calls = {"add": [], "remove": [], "resched": [], "enqueue": [], "events": []}
    monkeypatch.setattr(pl.scheduler, "add_capture_job", lambda p: calls["add"].append(p.id))
    monkeypatch.setattr(pl.scheduler, "remove_capture_job", lambda pid: calls["remove"].append(pid))
    monkeypatch.setattr(pl.scheduler, "reschedule_capture_job", lambda p: calls["resched"].append((p.id, p.interval_seconds)))

    async def _enqueue(**kw):
        calls["enqueue"].append(kw)
        return {"generation_id": "t", "position": 1}

    async def _emit(*a, **kw):
        calls["events"].append(a)

    monkeypatch.setattr(pl.generation_queue, "enqueue_generation", _enqueue)
    monkeypatch.setattr(pl.events, "emit", _emit)
    return calls


def _status(state, *, job_id=1, name="benchy.gcode", est=None):
    return {"state": state, "job_id": job_id, "progress": 0,
            "gcode_name": name,
            "estimated_seconds": est}


async def _run(db, cfg, status):
    return await pl._reconcile(db, cfg, status)


@pytest.mark.asyncio
async def test_start_creates_print_job_with_computed_interval(db, fakes):
    s = _stream(db)
    cfg = _cfg(stream_id=s.id)
    await _run(db, cfg, _status("PRINTING", est=36000))
    pj = db.query(PrintJob).one()
    assert pj.status == "printing"
    assert pj.gcode_name == "benchy.gcode"
    assert pj.interval_seconds == 72  # 36000 / (20*25)
    profile = db.query(Profile).filter(Profile.managed_by == "prusalink").one()
    assert profile.enabled is True
    assert profile.interval_seconds == 72
    assert fakes["add"] == [profile.id]
    assert fakes["events"][0][0] == "print_started"


@pytest.mark.asyncio
async def test_start_without_estimate_uses_default_then_recomputes_once(db, fakes):
    s = _stream(db)
    cfg = _cfg(stream_id=s.id)
    await _run(db, cfg, _status("PRINTING", est=None))
    pj = db.query(PrintJob).one()
    assert pj.interval_seconds == 10  # default
    assert pj.estimated_seconds is None
    # estimate appears on a later poll -> recompute exactly once
    await _run(db, cfg, _status("PRINTING", est=36000))
    db.refresh(pj)
    assert pj.interval_seconds == 72
    assert fakes["resched"] == [(db.query(Profile).one().id, 72)]
    # further polls with a different estimate do NOT recompute again
    await _run(db, cfg, _status("PRINTING", est=50000))
    db.refresh(pj)
    assert pj.interval_seconds == 72


@pytest.mark.asyncio
async def test_finish_closes_job_and_enqueues_named_render(db, fakes):
    s = _stream(db)
    cfg = _cfg(stream_id=s.id)
    await _run(db, cfg, _status("PRINTING", est=1500))
    await _run(db, cfg, _status("FINISHED"))
    pj = db.query(PrintJob).one()
    assert pj.status == "finished"
    assert pj.finished_at is not None
    profile = db.query(Profile).one()
    assert profile.enabled is False
    assert fakes["remove"] == [profile.id]
    (kw,) = fakes["enqueue"]
    assert kw["name"] == "benchy.gcode"
    assert kw["print_job_id"] == pj.id
    assert kw["fps_mode"] == "target_duration"
    assert kw["render_target_seconds"] == 20
    assert kw["timestamp_overlay"] is True
    assert kw["logo_overlay"] is False
    assert kw["deflicker"] == "medium"
    assert kw["period_start"] == pj.started_at
    assert fakes["events"][-1][0] == "print_finished"


@pytest.mark.asyncio
async def test_cancel_respects_generate_on_cancel(db, fakes):
    s = _stream(db)
    cfg = _cfg(stream_id=s.id, generate_on_cancel=False)
    await _run(db, cfg, _status("PRINTING", est=1500))
    await _run(db, cfg, _status("IDLE"))
    pj = db.query(PrintJob).one()
    assert pj.status == "cancelled"
    assert fakes["enqueue"] == []


@pytest.mark.asyncio
async def test_active_state_survives_restart_via_open_row(db, fakes):
    """Active = open print_jobs row; no in-memory/settings flag involved."""
    s = _stream(db)
    cfg = _cfg(stream_id=s.id)
    await _run(db, cfg, _status("PRINTING", est=1500))
    # simulate restart: nothing reset, next poll sees FINISHED
    await _run(db, cfg, _status("FINISHED"))
    assert db.query(PrintJob).one().status == "finished"
