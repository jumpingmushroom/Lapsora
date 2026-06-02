import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Capture


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
