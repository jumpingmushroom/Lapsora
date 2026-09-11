"""fps_mode / render_target_seconds must survive the trip from the request to
the generation call.

These columns existed on profiles and profile templates long before anything
read them: apply_template copied them onto the profile and the render path then
ignored them entirely, so configuring "target duration, 20s" on a preset was
silently discarded. These tests pin the wiring shut.
"""

from unittest.mock import patch

import pytest


def _create_stream(client):
    resp = client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"})
    return resp.json()["id"]


def _create_profile(client, stream_id, name="P1"):
    with patch("app.routers.profiles.scheduler"):
        return client.post(
            f"/api/streams/{stream_id}/profiles", json={"name": name}
        ).json()["id"]


# --- one-shot generate ---------------------------------------------------


def test_generate_forwards_length_mode(client):
    sid = _create_stream(client)
    pid = _create_profile(client, sid)

    with patch(
        "app.routers.timelapses.enqueue_generation",
        return_value={"generation_id": "x", "position": 1},
    ) as enqueue:
        resp = client.post(
            f"/api/profiles/{pid}/timelapses/generate",
            json={"fps_mode": "target_duration", "render_target_seconds": 45},
        )

    assert resp.status_code == 202, resp.text
    kwargs = enqueue.call_args.kwargs
    assert kwargs["fps_mode"] == "target_duration"
    assert kwargs["render_target_seconds"] == 45


def test_generate_defaults_to_fixed(client):
    """An unspecified mode must keep the old behaviour, not switch renders."""
    sid = _create_stream(client)
    pid = _create_profile(client, sid)

    with patch(
        "app.routers.timelapses.enqueue_generation",
        return_value={"generation_id": "x", "position": 1},
    ) as enqueue:
        resp = client.post(f"/api/profiles/{pid}/timelapses/generate", json={})

    assert resp.status_code == 202, resp.text
    kwargs = enqueue.call_args.kwargs
    assert kwargs["fps_mode"] == "fixed"
    assert kwargs["render_target_seconds"] == 20


@pytest.mark.parametrize("bad", [0, -5])
def test_generate_rejects_non_positive_target(client, bad):
    sid = _create_stream(client)
    pid = _create_profile(client, sid)
    resp = client.post(
        f"/api/profiles/{pid}/timelapses/generate",
        json={"fps_mode": "target_duration", "render_target_seconds": bad},
    )
    assert resp.status_code == 422


# --- schedules -----------------------------------------------------------


def test_schedule_persists_length_mode(client):
    sid = _create_stream(client)
    pid = _create_profile(client, sid)

    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post(
            "/api/timelapse-schedules/",
            json={
                "profile_id": pid,
                "cron_expression": "0 0 * * *",
                "fps_mode": "target_duration",
                "render_target_seconds": 30,
            },
        )

    assert resp.status_code == 201, resp.text
    assert resp.json()["fps_mode"] == "target_duration"
    assert resp.json()["render_target_seconds"] == 30


def test_schedule_defaults_preserve_existing_behaviour(client):
    """Schedules created before this column existed must keep fixed-fps."""
    sid = _create_stream(client)
    pid = _create_profile(client, sid)

    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post(
            "/api/timelapse-schedules/",
            json={"profile_id": pid, "cron_expression": "0 0 * * *"},
        )

    assert resp.status_code == 201, resp.text
    assert resp.json()["fps_mode"] == "fixed"
    assert resp.json()["render_target_seconds"] == 20


def test_schedule_trigger_forwards_length_mode(client):
    """Run-now must use the same settings as the cron firing would."""
    sid = _create_stream(client)
    pid = _create_profile(client, sid)

    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        sched = client.post(
            "/api/timelapse-schedules/",
            json={
                "profile_id": pid,
                "cron_expression": "0 0 * * *",
                "fps_mode": "target_duration",
                "render_target_seconds": 12,
            },
        ).json()

    with patch(
        "app.services.generation_queue.enqueue_generation",
        return_value={"generation_id": "x", "position": 1},
    ) as enqueue:
        resp = client.post(f"/api/timelapse-schedules/{sched['id']}/trigger")

    assert resp.status_code == 202, resp.text
    kwargs = enqueue.call_args.kwargs
    assert kwargs["fps_mode"] == "target_duration"
    assert kwargs["render_target_seconds"] == 12


def test_schedule_update_changes_length_mode(client):
    sid = _create_stream(client)
    pid = _create_profile(client, sid)

    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"), patch(
        "app.routers.timelapse_schedules.remove_timelapse_schedule_job"
    ):
        sched = client.post(
            "/api/timelapse-schedules/",
            json={"profile_id": pid, "cron_expression": "0 0 * * *"},
        ).json()
        resp = client.put(
            f"/api/timelapse-schedules/{sched['id']}",
            json={"fps_mode": "target_duration", "render_target_seconds": 8},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["fps_mode"] == "target_duration"
    assert resp.json()["render_target_seconds"] == 8
