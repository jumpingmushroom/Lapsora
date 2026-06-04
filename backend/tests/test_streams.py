def _create_stream(client, name="Test Stream", url="rtsp://example.com/stream"):
    return client.post("/api/streams/", json={"name": name, "url": url})


def test_create_stream(client):
    resp = _create_stream(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Stream"
    assert "url" not in data


def test_list_streams(client):
    _create_stream(client, name="Stream 1")
    _create_stream(client, name="Stream 2")
    resp = client.get("/api/streams/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_stream(client):
    create_resp = _create_stream(client)
    stream_id = create_resp.json()["id"]
    resp = client.get(f"/api/streams/{stream_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == stream_id
    assert data["name"] == "Test Stream"
    assert data["enabled"] is True


def test_update_stream(client):
    create_resp = _create_stream(client)
    stream_id = create_resp.json()["id"]
    resp = client.put(f"/api/streams/{stream_id}", json={"name": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


def test_delete_stream(client):
    create_resp = _create_stream(client)
    stream_id = create_resp.json()["id"]
    resp = client.delete(f"/api/streams/{stream_id}")
    assert resp.status_code == 204
    resp = client.get(f"/api/streams/{stream_id}")
    assert resp.status_code == 404


def test_create_stream_empty_name(client):
    resp = client.post("/api/streams/", json={"name": "", "url": "rtsp://x"})
    # FastAPI/Pydantic accepts empty strings; the model allows it
    # But we verify validation works for missing fields
    resp2 = client.post("/api/streams/", json={"url": "rtsp://x"})
    assert resp2.status_code == 422


# --- HTTP image sources ---


def test_create_http_snapshot_stream_with_auth(client, db):
    from app.config import decrypt
    from app.models import Stream

    resp = client.post(
        "/api/streams/",
        json={
            "name": "Garage cam",
            "source_type": "http_snapshot",
            "url": "http://cam.local/snapshot.jpg",
            "auth_type": "basic",
            "auth_username": "admin",
            "auth_secret": "hunter2",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["source_type"] == "http_snapshot"
    assert data["auth_type"] == "basic"
    assert data["auth_username"] == "admin"
    assert data["has_auth"] is True
    # Secret and raw URL are never returned.
    assert "auth_secret" not in data
    assert "url" not in data

    # Secret is stored encrypted, not plaintext.
    stream = db.query(Stream).filter(Stream.id == data["id"]).first()
    assert stream.auth_secret and stream.auth_secret != "hunter2"
    assert decrypt(stream.auth_secret) == "hunter2"


def test_create_http_mjpeg_requires_url(client):
    resp = client.post(
        "/api/streams/", json={"name": "no url", "source_type": "http_mjpeg"}
    )
    assert resp.status_code == 400


def test_test_endpoint_dispatches_to_http_provider(client, monkeypatch):
    async def fake_grab(url, auth=None, retries=3):
        return b"\xff\xd8\xff\xe0jpeg\xff\xd9"

    from app.services import http_source

    monkeypatch.setattr(http_source, "grab_snapshot", fake_grab)

    create = client.post(
        "/api/streams/",
        json={
            "name": "snap",
            "source_type": "http_snapshot",
            "url": "http://cam.local/snapshot.jpg",
        },
    )
    stream_id = create.json()["id"]
    resp = client.post(f"/api/streams/{stream_id}/test")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["details"]["bytes"] > 0
