"""POST /api/streams/test — probe a source before it is saved.

The id-bound test/preview endpoints forced the old flow: save a camera, open
it, test, read the failure, edit the URL. This endpoint tests first, so a typo
never leaves a broken row behind. The property that matters most here is that
nothing is persisted, on either outcome.
"""

import base64
import io

import numpy as np
import pytest
from PIL import Image

from app.models import Stream


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.full((60, 80, 3), 128, dtype="uint8"), "RGB").save(buf, "JPEG")
    return buf.getvalue()


def _stream_count(db) -> int:
    return db.query(Stream).count()


def test_successful_probe_returns_frame_and_saves_nothing(client, db, monkeypatch):
    jpeg = _jpeg()

    async def fake_grab(url, auth=None, retries=3):
        return jpeg

    from app.services import http_source

    monkeypatch.setattr(http_source, "grab_snapshot", fake_grab)

    resp = client.post(
        "/api/streams/test",
        json={"source_type": "http_snapshot", "url": "http://cam.local/snap.jpg"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert base64.b64decode(body["preview"]) == jpeg
    assert _stream_count(db) == 0


def test_failed_probe_reports_error_and_saves_nothing(client, db, monkeypatch):
    async def boom(url, auth=None, retries=3):
        raise RuntimeError("Connection refused")

    from app.services import http_source

    monkeypatch.setattr(http_source, "grab_snapshot", boom)

    resp = client.post(
        "/api/streams/test",
        json={"source_type": "http_snapshot", "url": "http://nope.local/snap.jpg"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "Connection refused" in body["message"]
    assert body["preview"] is None
    assert _stream_count(db) == 0


def test_preview_failure_does_not_fail_a_passing_test(client, monkeypatch):
    """A source can probe clean yet refuse a still. That's still a pass."""
    from app.services import providers

    async def ok(stream, db):
        return {"success": True, "message": "Connected", "details": {"codec": "h264"}}

    async def no_frame(stream, db):
        raise RuntimeError("decode failed")

    monkeypatch.setattr(providers, "test_source", ok)
    monkeypatch.setattr(providers, "grab_preview", no_frame)

    resp = client.post(
        "/api/streams/test", json={"source_type": "rtsp", "url": "rtsp://cam/1"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["preview"] is None
    assert body["details"] == {"codec": "h264"}


def test_auth_secret_is_used_but_never_echoed(client, monkeypatch):
    """The probe must apply credentials without returning them."""
    seen = {}

    async def fake_grab(url, auth=None, retries=3):
        seen["auth"] = auth
        return _jpeg()

    from app.services import http_source

    monkeypatch.setattr(http_source, "grab_snapshot", fake_grab)

    resp = client.post(
        "/api/streams/test",
        json={
            "source_type": "http_snapshot",
            "url": "http://cam.local/snap.jpg",
            "auth_type": "basic",
            "auth_username": "admin",
            "auth_secret": "hunter2",
        },
    )

    assert resp.status_code == 200, resp.text
    assert seen["auth"] is not None
    assert "hunter2" not in resp.text


@pytest.mark.parametrize(
    "payload",
    [
        {"source_type": "rtsp"},
        {"source_type": "http_snapshot"},
        {"source_type": "http_mjpeg"},
        {"source_type": "go2rtc"},
    ],
)
def test_missing_required_source_field_is_rejected(client, payload):
    """Test and Add must reject the same inputs."""
    resp = client.post("/api/streams/test", json=payload)
    assert resp.status_code == 400, resp.text


def test_route_does_not_shadow_an_existing_camera(client, monkeypatch):
    """'/streams/test' must not be swallowed by '/streams/{stream_id}/...'."""
    from app.services import providers

    async def ok(stream, db):
        return {"success": True, "message": "Connected", "details": None}

    async def frame(stream, db):
        return _jpeg()

    monkeypatch.setattr(providers, "test_source", ok)
    monkeypatch.setattr(providers, "grab_preview", frame)

    created = client.post("/api/streams/", json={"name": "cam", "url": "rtsp://a"})
    assert created.status_code == 201

    resp = client.post(
        "/api/streams/test", json={"source_type": "rtsp", "url": "rtsp://b"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True
