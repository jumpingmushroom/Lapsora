from unittest.mock import patch


def _create_stream(client):
    resp = client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"})
    return resp.json()["id"]


def _create_profile(client, stream_id, name="P1"):
    with patch("app.routers.profiles.scheduler"):
        return client.post(
            f"/api/streams/{stream_id}/profiles", json={"name": name}
        ).json()["id"]


def test_create_schedule_persists_render_settings(client):
    """motion_blur / codec / resolution / quality_preset must round-trip,
    not silently fall back to column defaults."""
    sid = _create_stream(client)
    pid = _create_profile(client, sid)

    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post(
            "/api/timelapse-schedules/",
            json={
                "profile_id": pid,
                "name": "nightly",
                "cron_expression": "0 0 * * *",
                "motion_blur": "high",
                "codec": "h265",
                "output_width": 1280,
                "output_height": 720,
                "quality_preset": "high",
            },
        )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["motion_blur"] == "high"
    assert data["codec"] == "h265"
    assert data["output_width"] == 1280
    assert data["output_height"] == 720
    assert data["quality_preset"] == "high"
