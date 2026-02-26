def test_list_timelapses_empty(client):
    resp = client.get("/api/timelapses")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_nonexistent_timelapse(client):
    resp = client.get("/api/timelapses/9999")
    assert resp.status_code == 404
