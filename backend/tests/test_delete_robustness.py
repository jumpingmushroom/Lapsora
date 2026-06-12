"""Delete/cleanup robustness: a missing or unremovable file must never prevent
the DB rows from being purged, and must not abort a bulk operation mid-loop.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Capture, Profile, Stream, Timelapse


def _seed_profile(db) -> Profile:
    s = Stream(name="S", url="enc")
    db.add(s)
    db.commit()
    db.refresh(s)
    p = Profile(stream_id=s.id, name="P")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_delete_capture_with_missing_file_still_removes_row(client, db):
    p = _seed_profile(db)
    c = Capture(profile_id=p.id, file_path="captures/gone.jpg")
    db.add(c)
    db.commit()
    db.refresh(c)

    resp = client.delete(f"/api/captures/{c.id}")
    assert resp.status_code == 204
    assert db.get(Capture, c.id) is None


def test_bulk_delete_captures_continues_past_missing_file(client, db, tmp_path):
    p = _seed_profile(db)
    present = tmp_path / "captures" / "present.jpg"
    present.parent.mkdir(parents=True)
    present.write_bytes(b"x")

    c1 = Capture(profile_id=p.id, file_path="captures/present.jpg")
    c2 = Capture(profile_id=p.id, file_path="captures/missing.jpg")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    with patch("app.routers.captures.settings.DATA_DIR", str(tmp_path)):
        resp = client.request("DELETE", "/api/captures/bulk", json={"ids": [c1.id, c2.id]})

    assert resp.status_code == 204
    assert db.get(Capture, c1.id) is None
    assert db.get(Capture, c2.id) is None
    assert not present.exists()  # the file that existed was removed


def test_delete_timelapse_with_missing_file_still_removes_row(client, db):
    p = _seed_profile(db)
    tl = Timelapse(profile_id=p.id, file_path="/tmp/nope/missing.mp4", thumbnail_path=None)
    db.add(tl)
    db.commit()
    db.refresh(tl)

    resp = client.delete(f"/api/timelapses/{tl.id}")
    assert resp.status_code == 204
    assert db.get(Timelapse, tl.id) is None


def test_cleanup_old_capture_missing_file_still_deletes_row(tmp_path):
    """run_profile_cleanup's age-based loop must not raise when an expired
    capture's file is already gone — the row must still be deleted."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    old = datetime.now(UTC) - timedelta(days=40)
    seed = TestSession()
    # FK enforcement requires a real parent profile (id 1 on a fresh DB).
    seed.add(Stream(id=1, name="S", url="enc"))
    seed.add(Profile(id=1, stream_id=1, name="P"))
    seed.commit()
    seed.add(Capture(profile_id=1, file_path="captures/old_missing.jpg", captured_at=old))
    seed.commit()
    seed.close()

    from app.services import retention

    with patch.object(retention, "SessionLocal", TestSession), patch.object(
        retention.settings, "DATA_DIR", str(tmp_path)
    ):
        summary = asyncio.run(
            retention.run_profile_cleanup(
                profile_id=1, capture_retention_days=30, timelapse_retention_days=90
            )
        )

    assert summary["captures_deleted"] == 1
    check = TestSession()
    remaining = check.query(Capture).all()
    check.close()
    assert remaining == []
