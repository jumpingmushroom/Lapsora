"""Render boundaries that cut a capture window in half.

The reported bug: a sunset-to-sunrise plan rendered daily at 00:05 produced the
tail of one night, a fourteen-hour gap, then the head of the next — two half
nights from different nights, stitched together. Midnight is the worst possible
pivot for an overnight window because it lands in the middle of every one.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Profile, Setting, Stream
from app.services.render_boundary import (
    SAFE_HOUR,
    boundary_splits_window,
    captures_continuously,
    describe_period,
    parse_cron_time,
    realign_cron,
    safe_boundary,
)


@pytest.fixture
def oslo(db):
    """Location, so the sun branch resolves rather than allowing everything."""
    db.add(Setting(key="location_latitude", value="59.91"))
    db.add(Setting(key="location_longitude", value="10.75"))
    db.commit()


def _plan(db, **kw):
    stream = Stream(name="cam", url="", source_type="rtsp")
    db.add(stream)
    db.flush()
    profile = Profile(
        stream_id=stream.id,
        name=kw.pop("name", "plan"),
        interval_seconds=kw.pop("interval_seconds", 60),
        created_at=datetime.now(UTC) - timedelta(days=1),
        **kw,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


# --- parsing ---------------------------------------------------------------


def test_parses_a_fixed_time():
    assert parse_cron_time("5 0 * * *") == (0, 5)
    assert parse_cron_time("0 12 * * 0") == (12, 0)


@pytest.mark.parametrize("expr", ["*/5 * * * *", "0 */2 * * *", "0 1,13 * * *", "bad", "0 12 * *"])
def test_refuses_expressions_with_no_single_boundary(expr):
    """A cron firing repeatedly has no one boundary to reason about, and no
    safe rewrite to offer."""
    assert parse_cron_time(expr) is None


def test_an_unparseable_cron_is_returned_untouched(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="night")
    assert realign_cron(plan, db, "*/5 * * * *") == "*/5 * * * *"


# --- detection -------------------------------------------------------------


def test_midnight_splits_an_overnight_sun_window(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="night")
    assert boundary_splits_window(plan, db, 0, 5) is True


def test_midday_does_not_split_an_overnight_sun_window(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="night")
    assert boundary_splits_window(plan, db, SAFE_HOUR, 0) is False


def test_midnight_splits_a_manual_window_that_wraps(db, oslo):
    """The same fault, unreported: 22:00-04:00 spans midnight too."""
    plan = _plan(db, capture_mode="manual", active_start_time="22:00", active_end_time="04:00")
    assert boundary_splits_window(plan, db, 0, 5) is True
    assert boundary_splits_window(plan, db, SAFE_HOUR, 0) is False


def test_a_daytime_manual_window_is_fine_at_midnight(db, oslo):
    plan = _plan(db, capture_mode="manual", active_start_time="06:00", active_end_time="20:00")
    assert boundary_splits_window(plan, db, 0, 5) is False


def test_an_always_on_plan_has_no_session_to_split(db, oslo):
    plan = _plan(db, capture_mode="always")
    assert boundary_splits_window(plan, db, 0, 5) is False
    assert captures_continuously(plan, db) is False


def test_daylight_only_is_fine_at_midnight(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="daylight")
    assert boundary_splits_window(plan, db, 0, 5) is False


# --- correction ------------------------------------------------------------


def test_a_splitting_daily_cron_moves_to_midday(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="night")
    assert realign_cron(plan, db, "5 0 * * *") == "0 12 * * *"


def test_weekly_keeps_its_day_and_only_moves_the_time(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="night")
    assert realign_cron(plan, db, "30 0 * * 0") == "0 12 * * 0"


def test_monthly_keeps_its_day_of_month(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="night")
    assert realign_cron(plan, db, "0 1 1 * *") == "0 12 1 * *"


def test_a_clean_boundary_is_left_alone(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="daylight")
    assert realign_cron(plan, db, "5 0 * * *") == "5 0 * * *"


def test_safe_boundary_returns_the_original_when_it_is_already_clean(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="daylight")
    assert safe_boundary(plan, db, 0, 5) == (0, 5)


# --- the case with no answer ----------------------------------------------


def test_a_round_the_clock_plan_admits_there_is_no_clean_boundary(db, oslo):
    """daylight + night is active all day. Pretending midday helps would be
    worse than the bug."""
    plan = _plan(db, capture_mode="sun", sun_events="daylight,night")
    assert captures_continuously(plan, db) is True
    assert safe_boundary(plan, db, 0, 5) is None


def test_a_round_the_clock_plan_keeps_its_cron(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="daylight,night")
    assert realign_cron(plan, db, "5 0 * * *") == "5 0 * * *"


# --- labelling -------------------------------------------------------------


def test_an_overnight_plan_calls_its_daily_period_nightly(db, oslo):
    plan = _plan(db, capture_mode="sun", sun_events="night")
    assert describe_period(plan, db, "daily") == "nightly"


def test_an_ordinary_plan_keeps_the_preset_name(db, oslo):
    plan = _plan(db, capture_mode="always")
    assert describe_period(plan, db, "daily") == "daily"


# --- seasonality -----------------------------------------------------------


def test_detection_samples_across_the_year(db, oslo, monkeypatch):
    """A boundary safe in one season and splitting in another is still a bug.
    Every sample must be consulted, not just the first."""
    plan = _plan(db, capture_mode="sun", sun_events="night")
    seen = []

    from app.services import capture
    real = capture._is_within_active_window

    def spy(profile, session, when):
        seen.append(when.month)
        return real(profile, session, when)

    monkeypatch.setattr(capture, "_is_within_active_window", spy)
    # A boundary that never splits forces every sample to be evaluated.
    boundary_splits_window(plan, db, SAFE_HOUR, 0)

    assert sorted(set(seen)) == [1, 4, 7, 10]


# --- schedule creation uses it --------------------------------------------


def _api_plan(client, capture_mode="sun", sun_events="night"):
    from unittest.mock import patch
    sid = client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"}).json()["id"]
    with patch("app.routers.profiles.scheduler"):
        return client.post(
            f"/api/streams/{sid}/profiles",
            json={"name": "Night", "capture_mode": capture_mode, "sun_events": sun_events},
        ).json()["id"]


def test_a_daily_preset_on_an_overnight_plan_is_created_at_midday(client, db, oslo):
    """The bug, at its source: the wizard offers "Every day" by default, and
    that must not produce a boundary in the middle of every night."""
    from unittest.mock import patch
    pid = _api_plan(client)
    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post(
            "/api/timelapse-schedules/", json={"profile_id": pid, "preset": "daily"}
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["cron_expression"] == "0 12 * * *"
    assert resp.json()["period_label"] == "nightly"


def test_a_daily_preset_on_an_ordinary_plan_is_unchanged(client, db, oslo):
    from unittest.mock import patch
    pid = _api_plan(client, capture_mode="always", sun_events="")
    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post(
            "/api/timelapse-schedules/", json={"profile_id": pid, "preset": "daily"}
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["cron_expression"] == "5 0 * * *"
    assert resp.json()["period_label"] == "daily"


def test_a_custom_cron_is_never_second_guessed(client, db, oslo):
    """A preset is ours to place; a cron the user typed is theirs."""
    from unittest.mock import patch
    pid = _api_plan(client)
    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post(
            "/api/timelapse-schedules/",
            json={"profile_id": pid, "cron_expression": "5 0 * * *"},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["cron_expression"] == "5 0 * * *"


def test_switching_preset_on_an_existing_schedule_realigns_it(client, db, oslo):
    from unittest.mock import patch
    pid = _api_plan(client)
    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"), patch(
        "app.routers.timelapse_schedules.remove_timelapse_schedule_job"
    ):
        sched = client.post(
            "/api/timelapse-schedules/",
            json={"profile_id": pid, "cron_expression": "0 3 * * *"},
        ).json()
        resp = client.put(
            f"/api/timelapse-schedules/{sched['id']}", json={"preset": "weekly"}
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["cron_expression"] == "0 12 * * 0"


def test_a_round_the_clock_plan_is_flagged_rather_than_moved(client, db, oslo):
    from unittest.mock import patch
    pid = _api_plan(client, sun_events="daylight,night")
    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post(
            "/api/timelapse-schedules/", json={"profile_id": pid, "preset": "daily"}
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["cron_expression"] == "5 0 * * *"
    assert resp.json()["captures_continuously"] is True


# --- the diagnostic finds and fixes what already exists --------------------


def _night_camera_capturing(client, db, oslo_unused=None):
    """A camera with an overnight plan, frames landing, and a daily schedule
    created with a cron that splits — the state the live instance was in."""
    from unittest.mock import patch
    from app.models import Capture, TimelapseSchedule
    sid = client.post("/api/streams/", json={"name": "Front", "url": "rtsp://x"}).json()["id"]
    with patch("app.routers.profiles.scheduler"):
        pid = client.post(
            f"/api/streams/{sid}/profiles",
            json={"name": "Sunset to sunrise", "capture_mode": "sun", "sun_events": "night"},
        ).json()["id"]
    db.add(TimelapseSchedule(profile_id=pid, name="Daily", preset="daily",
                             cron_expression="5 0 * * *", enabled=True))
    db.add(Capture(profile_id=pid, file_path="/tmp/a.jpg", file_size=1,
                   captured_at=datetime.now(UTC) - timedelta(seconds=5)))
    db.commit()
    return sid, pid


def test_the_diagnostic_reports_a_splitting_schedule(client, db, oslo, monkeypatch):
    """Everything else reports green for this: the frames are all present and
    correct, the schedule runs, the renders succeed. It is only findable by
    watching a video, which is why the diagnostic has to say it.

    Uses a manual 22:00-04:00 window and a 23:00 'now' so both the window check
    and the boundary sampling run for real — no patching of the rule itself.
    """
    from unittest.mock import patch
    from app.models import Capture, Stream, TimelapseSchedule
    from app.services import scheduler as scheduler_module
    from app.services.diagnostics import build_diagnostics

    class _Stub:
        running = True
        def get_job(self, job_id): return object()
    monkeypatch.setattr(scheduler_module, "scheduler", _Stub())

    sid = client.post("/api/streams/", json={"name": "Front", "url": "rtsp://x"}).json()["id"]
    with patch("app.routers.profiles.scheduler"):
        pid = client.post(
            f"/api/streams/{sid}/profiles",
            json={
                "name": "Overnight",
                "capture_mode": "manual",
                "active_start_time": "22:00",
                "active_end_time": "04:00",
            },
        ).json()["id"]

    now = datetime(2026, 9, 15, 23, 0).astimezone()
    db.add(TimelapseSchedule(profile_id=pid, name="Daily", preset="daily",
                             cron_expression="5 0 * * *", enabled=True))
    db.add(Capture(profile_id=pid, file_path="/tmp/a.jpg", file_size=1,
                   captured_at=now - timedelta(seconds=5)))
    db.commit()

    result = build_diagnostics(db.get(Stream, sid), db, now=now)

    assert result["action"] == "fix_schedule_boundary"
    assert result["status"] == "idle"
    assert "splitting" in result["summary"]
    assert "00:05" in result["summary"]


def test_realign_moves_a_splitting_schedule_and_clears_its_preset(client, db, oslo):
    from unittest.mock import patch
    from app.models import TimelapseSchedule
    sid, pid = _night_camera_capturing(client, db)

    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"), patch(
        "app.routers.timelapse_schedules.remove_timelapse_schedule_job"
    ):
        resp = client.post(f"/api/timelapse-schedules/realign?stream_id={sid}")

    assert resp.status_code == 200, resp.text
    assert len(resp.json()["moved"]) == 1
    sched = db.query(TimelapseSchedule).filter(TimelapseSchedule.profile_id == pid).one()
    assert sched.cron_expression == "0 12 * * *"
    # The preset named a time it no longer fires at, so the list must describe
    # it from the cron instead.
    assert sched.preset is None


def test_realign_leaves_a_clean_schedule_alone(client, db, oslo):
    from unittest.mock import patch
    from app.models import TimelapseSchedule
    sid = client.post("/api/streams/", json={"name": "Front", "url": "rtsp://x"}).json()["id"]
    with patch("app.routers.profiles.scheduler"):
        pid = client.post(f"/api/streams/{sid}/profiles",
                          json={"name": "Day", "capture_mode": "always"}).json()["id"]
    db.add(TimelapseSchedule(profile_id=pid, name="Daily", preset="daily",
                             cron_expression="5 0 * * *", enabled=True))
    db.commit()

    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"), patch(
        "app.routers.timelapse_schedules.remove_timelapse_schedule_job"
    ):
        resp = client.post(f"/api/timelapse-schedules/realign?stream_id={sid}")

    assert resp.json()["moved"] == []
    sched = db.query(TimelapseSchedule).filter(TimelapseSchedule.profile_id == pid).one()
    assert sched.cron_expression == "5 0 * * *"
    assert sched.preset == "daily"


def test_the_render_boundary_endpoint_answers_for_a_plan(client, db, oslo):
    from unittest.mock import patch
    sid = client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"}).json()["id"]
    with patch("app.routers.profiles.scheduler"):
        night = client.post(f"/api/streams/{sid}/profiles",
                            json={"name": "N", "capture_mode": "sun", "sun_events": "night"}).json()["id"]
        always = client.post(f"/api/streams/{sid}/profiles",
                             json={"name": "A", "capture_mode": "always"}).json()["id"]

    assert client.get(f"/api/profiles/{night}/render-boundary").json()["splits_at_default"] is True
    assert client.get(f"/api/profiles/{always}/render-boundary").json()["splits_at_default"] is False
