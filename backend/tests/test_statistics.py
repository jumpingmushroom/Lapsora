from datetime import UTC, datetime, timedelta

from app.models import Capture


def _seed(db, profile_id, when, size=100):
    db.add(
        Capture(
            profile_id=profile_id,
            file_path=f"captures/{when.timestamp()}.jpg",
            file_size=size,
            captured_at=when,
        )
    )


def test_capture_activity_respects_cutoff_boundary(client, db):
    """The cutoff filter must include the boundary day and exclude older rows.

    Guards the switch from `date(captured_at) >= :cutoff` to the sargable
    `captured_at >= :cutoff`, which must stay behaviourally identical.
    """
    now = datetime.now(UTC)
    _seed(db, 1, now)
    _seed(db, 1, now - timedelta(days=5))
    _seed(db, 1, now - timedelta(days=5))
    # Exactly on the cutoff day (today - 30) at midnight -> must be included.
    boundary = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    _seed(db, 1, boundary)
    # Outside the window -> must be excluded.
    _seed(db, 1, now - timedelta(days=100))
    db.commit()

    resp = client.get("/api/statistics/capture-activity?days=30")
    assert resp.status_code == 200
    total = sum(point["count"] for point in resp.json())
    assert total == 4


def test_profile_storage_filters_by_profile(client, db):
    now = datetime.now(UTC)
    _seed(db, 1, now, size=500)
    _seed(db, 2, now, size=999)
    db.commit()

    resp = client.get("/api/statistics/profile-storage?days=30&profile_id=1")
    assert resp.status_code == 200
    data = resp.json()
    assert all(point["profile_id"] == 1 for point in data)
    assert sum(point["bytes"] for point in data) == 500
