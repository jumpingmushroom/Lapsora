"""The add-camera wizard's create sequence, end to end.

The wizard makes three calls in a row — create the camera, create a capture
plan from a preset (or custom), then schedule a render against that plan. Each
endpoint is covered on its own elsewhere; what this pins is the contract
*between* them, since a break there leaves a half-configured camera behind and
the wizard cannot roll back across three endpoints.
"""

from unittest.mock import patch

import pytest

from app.models import Profile, TimelapseSchedule


@pytest.fixture
def no_scheduler():
    """Capture jobs and cron jobs both need a live scheduler; stub both out."""
    with patch("app.routers.profiles.scheduler"), patch(
        "app.routers.profile_templates.scheduler"
    ), patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        yield


def _create_preset(client) -> int:
    return client.post(
        "/api/profile-templates/",
        json={
            "name": "Slow clouds",
            "category": "Nature",
            "interval_seconds": 120,
            "fps_mode": "target_duration",
            "render_target_seconds": 25,
            "render_format": "mp4",
        },
    ).json()["id"]


def test_wizard_sequence_from_a_preset(client, db, no_scheduler):
    stream_id = client.post(
        "/api/streams/", json={"name": "Front Yard", "url": "rtsp://cam/1"}
    ).json()["id"]

    preset_id = _create_preset(client)
    profile = client.post(
        f"/api/profile-templates/{preset_id}/apply",
        json={"stream_id": stream_id, "name": "Front Yard"},
    )
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["id"]

    # The wizard sends a preset with no cron_expression and lets the backend
    # resolve it, so the schedule reads the same as every other daily one.
    sched = client.post(
        "/api/timelapse-schedules/",
        json={"profile_id": profile_id, "preset": "daily", "name": "Daily"},
    )
    assert sched.status_code == 201, sched.text
    assert sched.json()["cron_expression"] == "5 0 * * *"
    assert sched.json()["lookback_hours"] == 24

    # The plan carries the preset's render intent, which the render dialog
    # then seeds itself from.
    stored = db.get(Profile, profile_id)
    assert stored.name == "Front Yard"
    assert stored.interval_seconds == 120
    assert stored.fps_mode == "target_duration"
    assert stored.render_target_seconds == 25
    assert db.query(TimelapseSchedule).count() == 1


def test_wizard_sequence_with_a_custom_plan(client, db, no_scheduler):
    stream_id = client.post(
        "/api/streams/", json={"name": "Shed", "url": "rtsp://cam/2"}
    ).json()["id"]

    profile = client.post(
        f"/api/streams/{stream_id}/profiles",
        json={
            "name": "Shed",
            "interval_seconds": 300,
            "resolution_width": None,
            "resolution_height": None,
            "quality": 85,
        },
    )
    assert profile.status_code == 201, profile.text
    stored = db.get(Profile, profile.json()["id"])
    assert stored.interval_seconds == 300
    # "Source resolution" in the wizard means no explicit size.
    assert stored.resolution_width is None
    assert stored.resolution_height is None


def test_manual_render_choice_creates_no_schedule(client, db, no_scheduler):
    stream_id = client.post(
        "/api/streams/", json={"name": "Garage", "url": "rtsp://cam/3"}
    ).json()["id"]
    client.post(f"/api/streams/{stream_id}/profiles", json={"name": "Garage"})

    assert db.query(TimelapseSchedule).count() == 0


def test_weekly_choice_resolves_to_the_shared_preset(client, db, no_scheduler):
    stream_id = client.post(
        "/api/streams/", json={"name": "Roof", "url": "rtsp://cam/4"}
    ).json()["id"]
    profile_id = client.post(
        f"/api/streams/{stream_id}/profiles", json={"name": "Roof"}
    ).json()["id"]

    sched = client.post(
        "/api/timelapse-schedules/",
        json={"profile_id": profile_id, "preset": "weekly", "name": "Weekly"},
    )
    assert sched.status_code == 201, sched.text
    assert sched.json()["cron_expression"] == "30 0 * * 0"
    assert sched.json()["lookback_hours"] == 168
