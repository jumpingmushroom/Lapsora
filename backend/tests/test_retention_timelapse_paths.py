"""Timelapse rows must survive the orphan sweep when their file is on disk.

Timelapse paths are stored with the DATA_DIR prefix already applied -- the
renderer builds them with ``os.path.join(settings.DATA_DIR, "timelapses", ...)``
and the download endpoints open ``file_path`` directly -- while capture paths
are stored relative to DATA_DIR. Joining DATA_DIR onto a timelapse path
produced ``data/data/timelapses/...``, so every render looked orphaned. The
sweep's "all rows orphaned" guard masked it for profiles with >= 5 renders, and
a profile with fewer lost the records of files still present on disk.

DATA_DIR is relative in the real deployment ("data"), so these tests chdir into
a temp root and use relative paths -- an absolute path would take the
``os.path.isabs`` short-circuit and never exercise the bug.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Profile, Stream, Timelapse

DATA_DIR = "data"  # relative, as in the real config


def _seed(n_timelapses):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    out_dir = os.path.join(DATA_DIR, "timelapses", "1")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "captures"), exist_ok=True)

    s = TestSession()
    s.add(Stream(id=1, name="S", url="enc"))
    s.add(Profile(id=1, stream_id=1, name="P"))
    s.commit()
    rels = []
    for i in range(n_timelapses):
        rel = os.path.join(out_dir, f"daily_{i}.mkv")       # "data/timelapses/1/daily_0.mkv"
        thumb = rel.replace(".mkv", "_thumb.jpg")
        open(rel, "wb").write(b"video")
        open(thumb, "wb").write(b"thumb")
        s.add(Timelapse(profile_id=1, file_path=rel, thumbnail_path=thumb,
                        format="mkv", fps=24, created_at=datetime.now(UTC)))
        rels.append(rel)
    s.commit(); s.close()
    return TestSession, rels


def _run(TestSession, **kw):
    from app.services import retention
    with patch.object(retention, "SessionLocal", TestSession), \
            patch.object(retention.settings, "DATA_DIR", DATA_DIR):
        return asyncio.run(retention.run_profile_cleanup(profile_id=1, **kw))


@pytest.mark.parametrize("n", [1, 4, 5, 10])
def test_present_timelapses_are_never_orphaned(tmp_path, monkeypatch, n):
    """Regardless of row count -- above or below the sweep's guard threshold."""
    monkeypatch.chdir(tmp_path)
    TestSession, _ = _seed(n)

    summary = _run(TestSession, capture_retention_days=32, timelapse_retention_days=3650)

    assert summary["orphan_records_cleaned"] == 0
    assert summary["timelapses_deleted"] == 0
    check = TestSession()
    assert check.query(Timelapse).count() == n, "a present file's record was deleted"
    check.close()


def test_genuinely_missing_timelapse_is_still_collected(tmp_path, monkeypatch):
    """The sweep must keep working -- a row whose file is gone is still removed."""
    monkeypatch.chdir(tmp_path)
    TestSession, rels = _seed(1)
    os.unlink(rels[0])

    summary = _run(TestSession, capture_retention_days=32, timelapse_retention_days=3650)

    assert summary["orphan_records_cleaned"] == 1
    check = TestSession()
    assert check.query(Timelapse).count() == 0
    check.close()


def test_age_based_deletion_removes_the_real_file(tmp_path, monkeypatch):
    """Retention deletion must unlink the actual file, not a data/data/ path."""
    monkeypatch.chdir(tmp_path)
    TestSession, rels = _seed(1)
    check = TestSession()
    check.query(Timelapse).one().created_at = datetime.now(UTC) - timedelta(days=10)
    check.commit(); check.close()

    summary = _run(TestSession, capture_retention_days=32, timelapse_retention_days=1)

    assert summary["timelapses_deleted"] == 1
    assert not os.path.exists(rels[0]), "file left behind on disk after deletion"
