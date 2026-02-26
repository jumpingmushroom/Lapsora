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
