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


def test_create_profile(client):
    sid = _create_stream(client)
    resp = _create_profile(client, sid)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Profile 1"
    assert data["stream_id"] == sid
    assert data["interval_seconds"] == 30


def test_list_profiles(client):
    sid = _create_stream(client)
    _create_profile(client, sid, "P1")
    _create_profile(client, sid, "P2")
    resp = client.get(f"/api/streams/{sid}/profiles")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_profile(client):
    sid = _create_stream(client)
    create_resp = _create_profile(client, sid)
    pid = create_resp.json()["id"]
    resp = client.get(f"/api/profiles/{pid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == pid


def test_update_profile(client):
    sid = _create_stream(client)
    create_resp = _create_profile(client, sid)
    pid = create_resp.json()["id"]
    with patch("app.routers.profiles.scheduler"):
        resp = client.put(
            f"/api/profiles/{pid}", json={"interval_seconds": 120}
        )
    assert resp.status_code == 200
    assert resp.json()["interval_seconds"] == 120


def test_delete_profile(client):
    sid = _create_stream(client)
    create_resp = _create_profile(client, sid)
    pid = create_resp.json()["id"]
    with patch("app.routers.profiles.scheduler"):
        resp = client.delete(f"/api/profiles/{pid}")
    assert resp.status_code == 204
    resp = client.get(f"/api/profiles/{pid}")
    assert resp.status_code == 404


def test_create_profile_nonexistent_stream(client):
    with patch("app.routers.profiles.scheduler"):
        resp = client.post(
            "/api/streams/9999/profiles",
            json={"name": "X", "interval_seconds": 60},
        )
    assert resp.status_code == 404
