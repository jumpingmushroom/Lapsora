import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Capture, Profile, Stream, Timelapse


def _seed_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_orphan_cleanup_removes_only_missing_files(tmp_path):
    """run_profile_cleanup must delete DB rows whose file is gone and keep the rest.

    Guards the orphan-scan refactor (column-only select + batched DELETE),
    which must remove exactly the same rows as the previous per-row version.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    (tmp_path / "captures").mkdir()
    present_rel = "captures/present.jpg"
    (tmp_path / present_rel).write_bytes(b"x")

    seed = TestSession()
    # FK enforcement requires a real parent profile (id 1 on a fresh DB).
    seed.add(Stream(id=1, name="S", url="enc"))
    seed.add(Profile(id=1, stream_id=1, name="P"))
    seed.commit()
    # Recent timestamps so the age-based deletion step leaves these for the
    # orphan scan to evaluate.
    seed.add(Capture(profile_id=1, file_path=present_rel, captured_at=datetime.now(UTC)))
    seed.add(Capture(profile_id=1, file_path="captures/missing.jpg", captured_at=datetime.now(UTC)))
    seed.commit()
    seed.close()

    from app.services import retention

    with patch.object(retention, "SessionLocal", TestSession), \
            patch.object(retention.settings, "DATA_DIR", str(tmp_path)):
        summary = asyncio.run(
            retention.run_profile_cleanup(
                profile_id=1, capture_retention_days=32, timelapse_retention_days=90
            )
        )

    assert summary["orphan_records_cleaned"] == 1

    check = TestSession()
    remaining = check.query(Capture).all()
    check.close()
    assert len(remaining) == 1
    assert remaining[0].file_path == present_rel


def test_orphan_sweep_skips_when_all_rows_appear_orphaned(tmp_path):
    """F-2: a permission flap on the media root makes os.path.exists return
    False for every file. The orphan sweep must NOT then wipe every record —
    that is data loss, not reconciliation."""
    TestSession = _seed_engine()

    # The media root exists and is readable, so the guard reaches the
    # all-rows-orphaned check rather than the unreadable-root branch.
    (tmp_path / "captures").mkdir()

    seed = TestSession()
    seed.add(Stream(id=1, name="S", url="enc"))
    seed.add(Profile(id=1, stream_id=1, name="P"))
    seed.commit()
    now = datetime.now(UTC)
    # Six recent captures (survive age-based delete) whose files are all missing.
    for i in range(6):
        seed.add(Capture(profile_id=1, file_path=f"captures/gone_{i}.jpg", captured_at=now))
    seed.commit()
    seed.close()

    from app.services import retention

    with patch.object(retention, "SessionLocal", TestSession), \
            patch.object(retention.settings, "DATA_DIR", str(tmp_path)):
        summary = asyncio.run(
            retention.run_profile_cleanup(
                profile_id=1, capture_retention_days=30, timelapse_retention_days=90
            )
        )

    assert summary["orphan_records_cleaned"] == 0
    check = TestSession()
    assert check.query(Capture).count() == 6
    check.close()


def test_age_cleanup_removes_timelapse_thumbnail(tmp_path):
    """F-7: age-based timelapse deletion must unlink the thumbnail too, not just
    the video, or thumbnails leak on disk forever."""
    TestSession = _seed_engine()

    tl_dir = tmp_path / "timelapses"
    tl_dir.mkdir()
    video = tl_dir / "old.mp4"
    thumb = tl_dir / "old_thumb.jpg"
    video.write_bytes(b"v")
    thumb.write_bytes(b"t")

    seed = TestSession()
    seed.add(Stream(id=1, name="S", url="enc"))
    seed.add(Profile(id=1, stream_id=1, name="P"))
    seed.commit()
    old = datetime.now(UTC) - timedelta(days=100)
    seed.add(Timelapse(
        profile_id=1,
        file_path="timelapses/old.mp4",
        thumbnail_path="timelapses/old_thumb.jpg",
        created_at=old,
    ))
    seed.commit()
    seed.close()

    from app.services import retention

    with patch.object(retention, "SessionLocal", TestSession), \
            patch.object(retention.settings, "DATA_DIR", str(tmp_path)):
        summary = asyncio.run(
            retention.run_profile_cleanup(
                profile_id=1, capture_retention_days=30, timelapse_retention_days=90
            )
        )

    assert summary["timelapses_deleted"] == 1
    assert not video.exists()
    assert not thumb.exists()
