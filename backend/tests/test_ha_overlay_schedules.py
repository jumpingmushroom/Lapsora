from unittest.mock import patch


def _create_stream(client):
    return client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"}).json()["id"]


def _create_profile(client, stream_id):
    with patch("app.routers.profiles.scheduler"):
        return client.post(f"/api/streams/{stream_id}/profiles", json={"name": "P1"}).json()["id"]


def test_schedule_persists_ha_overlay_fields(client):
    sid = _create_stream(client)
    pid = _create_profile(client, sid)
    with patch("app.routers.timelapse_schedules.add_timelapse_schedule_job"):
        resp = client.post("/api/timelapse-schedules/", json={
            "profile_id": pid,
            "name": "nightly",
            "cron_expression": "0 0 * * *",
            "ha_overlay": True,
            "ha_overlay_position": "bottom-left",
        })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["ha_overlay"] is True
    assert data["ha_overlay_position"] == "bottom-left"


def test_profile_roundtrips_ha_sensors_json(client):
    sid = _create_stream(client)
    with patch("app.routers.profiles.scheduler"):
        resp = client.post(f"/api/streams/{sid}/profiles", json={
            "name": "GH",
            "ha_sensors": '[{"entity_id":"sensor.t","label":"Temp","unit":"°C","icon":"thermometer"}]',
        })
    assert resp.status_code == 201, resp.text
    assert "sensor.t" in resp.json()["ha_sensors"]
