"""GET /api/profiles/{id}/captures/count.

Feeds two figures the UI could not previously state honestly: how long a render
will actually be, and roughly how large one frame is for this plan. The
distinction that matters is avg_bytes being None rather than 0 when nothing
recorded a size — callers omit the storage estimate instead of claiming the
frames are free.
"""

from datetime import UTC, datetime, timedelta

from app.models import Capture, Profile, Stream


def _seed(db, sizes, base=None):
    stream = Stream(name="cam", url="", source_type="rtsp")
    db.add(stream)
    db.flush()
    profile = Profile(stream_id=stream.id, name="plan", interval_seconds=60)
    db.add(profile)
    db.flush()

    base = base or datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    for i, size in enumerate(sizes):
        db.add(
            Capture(
                profile_id=profile.id,
                file_path=f"/tmp/{i}.jpg",
                file_size=size,
                captured_at=base + timedelta(minutes=i),
            )
        )
    db.commit()
    return profile.id, base


def test_counts_and_averages_all_frames(client, db):
    pid, _ = _seed(db, [100, 200, 300])

    body = client.get(f"/api/profiles/{pid}/captures/count").json()

    assert body["count"] == 3
    assert body["total_bytes"] == 600
    assert body["avg_bytes"] == 200


def test_restricts_to_the_requested_range(client, db):
    pid, base = _seed(db, [100] * 10)

    start = (base + timedelta(minutes=2)).isoformat()
    end = (base + timedelta(minutes=4)).isoformat()
    body = client.get(
        f"/api/profiles/{pid}/captures/count", params={"start": start, "end": end}
    ).json()

    # Inclusive at both ends: minutes 2, 3 and 4.
    assert body["count"] == 3
    assert body["total_bytes"] == 300


def test_empty_range_reports_zero_not_an_error(client, db):
    """The render dialog shows "nothing to render" off the back of this."""
    pid, base = _seed(db, [100, 100])

    far = (base + timedelta(days=365)).isoformat()
    body = client.get(f"/api/profiles/{pid}/captures/count", params={"start": far}).json()

    assert body["count"] == 0
    assert body["total_bytes"] == 0
    assert body["avg_bytes"] is None


def test_unsized_captures_give_no_average(client, db):
    """A plan whose rows never recorded a size must not read as zero-byte
    frames, or the storage estimate would claim capture is free."""
    pid, _ = _seed(db, [None, None])

    body = client.get(f"/api/profiles/{pid}/captures/count").json()

    assert body["count"] == 2
    assert body["avg_bytes"] is None


def test_average_ignores_unsized_rows(client, db):
    pid, _ = _seed(db, [100, None, 300])

    body = client.get(f"/api/profiles/{pid}/captures/count").json()

    assert body["count"] == 3
    # 400 bytes over the two rows that actually recorded one.
    assert body["avg_bytes"] == 200


def test_unknown_profile_is_empty_rather_than_a_404(client, db):
    body = client.get("/api/profiles/9999/captures/count").json()
    assert body["count"] == 0
    assert body["avg_bytes"] is None
