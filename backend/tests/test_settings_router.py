"""Settings router coverage for the network-independent (pure-DB) endpoints.

The homeassistant/prusalink/go2rtc endpoints run live reachability probes and
so can't be asserted on offline; those are exercised elsewhere. Here we cover
the config roundtrips and notification-URL CRUD that have no external calls.
"""


def test_health_config_roundtrip(client):
    resp = client.put(
        "/api/settings/health",
        json={"failure_threshold": 7, "low_disk_threshold_percent": 15},
    )
    assert resp.status_code == 200, resp.text
    got = client.get("/api/settings/health").json()
    assert got["failure_threshold"] == 7
    assert got["low_disk_threshold_percent"] == 15


def test_location_config_roundtrip(client):
    resp = client.put("/api/settings/location", json={"latitude": 59.33, "longitude": 18.07})
    assert resp.status_code == 200, resp.text
    got = client.get("/api/settings/location").json()
    assert got["latitude"] == 59.33
    assert got["longitude"] == 18.07


def test_time_format_roundtrip(client):
    assert client.put("/api/settings/time-format", json={"use_24h": True}).status_code == 200
    assert client.get("/api/settings/time-format").json()["use_24h"] is True
    assert client.put("/api/settings/time-format", json={"use_24h": False}).status_code == 200
    assert client.get("/api/settings/time-format").json()["use_24h"] is False


def test_notification_url_crud_and_url_never_returned(client):
    # Create
    resp = client.post(
        "/api/settings/notifications/urls",
        json={"label": "My webhook", "url": "https://hooks.example.com/abc"},
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    url_id = created["id"]
    assert created["label"] == "My webhook"
    # The raw (encrypted-at-rest) URL must never be echoed back to the client.
    assert "abc" not in (created.get("url") or "")

    # List
    listing = client.get("/api/settings/notifications").json()
    assert any(u["id"] == url_id for u in listing["urls"])
    assert "events" in listing

    # Delete
    assert client.delete(f"/api/settings/notifications/urls/{url_id}").status_code == 204
    listing2 = client.get("/api/settings/notifications").json()
    assert all(u["id"] != url_id for u in listing2["urls"])


def test_notification_event_toggles_persist(client):
    resp = client.put(
        "/api/settings/notifications/events",
        json={"timelapse_complete": False, "timelapse_failure": True},
    )
    assert resp.status_code == 200, resp.text
    events = client.get("/api/settings/notifications").json()["events"]
    assert events["timelapse_complete"] is False
    assert events["timelapse_failure"] is True


def test_prusalink_roundtrip_and_managed_profile(client, db, monkeypatch):
    from app.models import Profile, Stream
    from app.services import health_status

    async def _unreachable(*a, **kw):
        return False

    monkeypatch.setattr(health_status, "reachable", _unreachable)

    s = Stream(name="printer-cam", url="rtsp://x")
    db.add(s)
    db.commit()
    payload = {
        "base_url": "http://prusa.local", "username": "maker", "password": "pw",
        "stream_id": s.id, "poll_interval_seconds": 10,
        "generate_on_finish": True, "generate_on_cancel": False, "enabled": False,
        "clip_seconds": 30, "clip_fps": 30, "default_interval_seconds": 5,
        "min_interval_seconds": 2, "max_interval_seconds": 60,
        "timestamp_overlay": False, "logo_overlay": True, "deflicker": "high",
        "quality": 80, "ha_sensors": None,
    }
    resp = client.put("/api/settings/prusalink", json=payload)
    assert resp.status_code == 200, resp.text
    got = client.get("/api/settings/prusalink").json()
    assert got["stream_id"] == s.id
    assert got["clip_seconds"] == 30
    assert got["logo_overlay"] is True
    assert "password" not in got
    assert "profile_id" not in got
    # managed profile created + synced
    mp = db.query(Profile).filter(Profile.managed_by == "prusalink").one()
    assert mp.stream_id == s.id
    assert mp.quality == 80
    assert mp.render_target_seconds == 30
    assert mp.render_fps == 30
    assert mp.fps_mode == "target_duration"


def test_disabling_prusalink_mid_print_closes_orphaned_job(client, db, monkeypatch):
    """Disabling/unbinding PrusaLink while a print is in flight must not leave the
    managed profile enabled with its capture job running and the print_jobs row
    stuck at 'printing' forever (the managed profile is hidden from the UI and its
    API disable path 409s, so there'd be no other way to recover)."""
    from datetime import UTC, datetime

    from app.models import PrintJob, Profile, Stream
    from app.services import health_status

    async def _unreachable(*a, **kw):
        return False

    monkeypatch.setattr(health_status, "reachable", _unreachable)

    s = Stream(name="printer-cam", url="rtsp://x")
    db.add(s)
    db.commit()

    # Seed an already-bound + enabled managed profile and an in-flight print,
    # as if the poller had started a capture.
    profile = Profile(
        stream_id=s.id, name="3D Print (auto)", managed_by="prusalink",
        enabled=True, interval_seconds=10,
    )
    db.add(profile)
    db.commit()
    pj = PrintJob(
        gcode_name="benchy.gcode", stream_id=s.id, status="printing",
        started_at=datetime.now(UTC),
    )
    db.add(pj)
    db.commit()
    pj_id = pj.id

    payload = {
        "base_url": "http://prusa.local", "username": "maker", "password": "pw",
        "stream_id": s.id, "poll_interval_seconds": 10,
        "generate_on_finish": True, "generate_on_cancel": False, "enabled": False,
        "clip_seconds": 30, "clip_fps": 30, "default_interval_seconds": 5,
        "min_interval_seconds": 2, "max_interval_seconds": 60,
        "timestamp_overlay": False, "logo_overlay": True, "deflicker": "high",
        "quality": 80, "ha_sensors": None,
    }
    resp = client.put("/api/settings/prusalink", json=payload)
    assert resp.status_code == 200, resp.text

    db.refresh(profile)
    assert profile.enabled is False

    closed = db.query(PrintJob).filter(PrintJob.id == pj_id).one()
    assert closed.status == "cancelled"
    assert closed.finished_at is not None
