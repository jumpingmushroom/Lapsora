from unittest.mock import patch


def _create_stream(client):
    resp = client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"})
    return resp.json()["id"]


def _create_profile(client, stream_id, name="Profile 1"):
    with patch("app.routers.profiles.scheduler"):
        return client.post(
            f"/api/streams/{stream_id}/profiles",
            json={"name": name, "interval_seconds": 30},
        )


def test_list_timelapses_empty(client):
    resp = client.get("/api/timelapses")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_nonexistent_timelapse(client):
    resp = client.get("/api/timelapses/9999")
    assert resp.status_code == 404


def test_schedule_weather_style_defaults_to_glass(client):
    """Creating a schedule without specifying weather_style should default to 'glass'."""
    sid = _create_stream(client)
    profile_resp = _create_profile(client, sid)
    assert profile_resp.status_code == 201
    pid = profile_resp.json()["id"]

    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post(
            "/api/timelapse-schedules/",
            json={
                "profile_id": pid,
                "cron_expression": "5 0 * * *",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["weather_style"] == "glass"
