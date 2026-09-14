"""Cleanup schedule CRUD through the API.

cron_utils centralised four hand-rolled cron splits, but the import was missed
in this router — and `_validate_cron` caught bare Exception, so the resulting
NameError came back as "Invalid cron expression: name 'cron_trigger_kwargs' is
not defined". Creating any cleanup schedule failed, and it looked like bad user
input. cron_utils had thorough unit tests; nothing exercised this endpoint.
"""

from unittest.mock import patch

import pytest


def _plan(client):
    sid = client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"}).json()["id"]
    with patch("app.routers.profiles.scheduler"):
        return client.post(f"/api/streams/{sid}/profiles", json={"name": "P"}).json()["id"]


def test_a_cleanup_schedule_can_be_created(client):
    pid = _plan(client)
    with patch("app.routers.cleanup_schedules.add_cleanup_schedule_job"):
        resp = client.post(
            "/api/cleanup-schedules/",
            json={
                "profile_id": pid,
                "name": "Keep 30d",
                "capture_retention_days": 30,
                "timelapse_retention_days": 3650,
                "cron_expression": "0 3 * * *",
            },
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["capture_retention_days"] == 30
    assert body["timelapse_retention_days"] == 3650
    assert body["cron_expression"] == "0 3 * * *"


def test_a_weekly_cleanup_uses_standard_cron_day_numbering(client):
    """The reason cron_utils exists: day-of-week 0 is Sunday in cron, Monday in
    APScheduler. Creating one must not raise, and must keep the expression."""
    pid = _plan(client)
    with patch("app.routers.cleanup_schedules.add_cleanup_schedule_job"):
        resp = client.post(
            "/api/cleanup-schedules/",
            json={"profile_id": pid, "cron_expression": "0 3 * * 0"},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["cron_expression"] == "0 3 * * 0"


def test_a_cleanup_schedule_can_be_updated(client):
    pid = _plan(client)
    with patch("app.routers.cleanup_schedules.add_cleanup_schedule_job"), patch(
        "app.routers.cleanup_schedules.remove_cleanup_schedule_job"
    ):
        sched = client.post(
            "/api/cleanup-schedules/",
            json={"profile_id": pid, "cron_expression": "0 3 * * *"},
        ).json()
        resp = client.put(
            f"/api/cleanup-schedules/{sched['id']}",
            json={"capture_retention_days": 400, "cron_expression": "0 4 * * *"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["capture_retention_days"] == 400
    assert resp.json()["cron_expression"] == "0 4 * * *"


@pytest.mark.parametrize("expr", ["not a cron", "0 3 * *", "99 3 * * *"])
def test_a_genuinely_bad_cron_is_still_rejected(client, expr):
    """Narrowing the except must not stop real validation failures surfacing."""
    pid = _plan(client)
    resp = client.post(
        "/api/cleanup-schedules/", json={"profile_id": pid, "cron_expression": expr}
    )
    assert resp.status_code == 422, resp.text


def test_an_unknown_plan_is_rejected(client):
    resp = client.post(
        "/api/cleanup-schedules/", json={"profile_id": 9999, "cron_expression": "0 3 * * *"}
    )
    assert resp.status_code == 404
