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
