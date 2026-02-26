from unittest.mock import patch


def _create_stream_and_profile(client):
    sid = client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"}).json()["id"]
    with patch("app.routers.profiles.scheduler"):
        pid = client.post(
            f"/api/streams/{sid}/profiles",
            json={"name": "P", "interval_seconds": 60},
        ).json()["id"]
    return sid, pid


def test_list_captures_empty(client):
    _sid, pid = _create_stream_and_profile(client)
    resp = client.get(f"/api/profiles/{pid}/captures")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_nonexistent_capture_image(client):
    resp = client.get("/api/captures/9999/image")
    assert resp.status_code == 404
