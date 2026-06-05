"""Regression tests for capture-gap alerting.

The gap check compares a timezone-aware ``datetime.now(UTC)`` against datetimes
read back from SQLite (which are naive). Before the fix this raised a
``TypeError`` that the per-profile ``try/except`` swallowed, so an alert was
never emitted — the feature was silently dead.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Capture, Profile, Stream


def _session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _seed(Session, *, last_capture_age: timedelta):
    s = Session()
    created = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    captured = datetime.now(UTC).replace(tzinfo=None) - last_capture_age
    stream = Stream(name="cam", url="enc://x", source_type="rtsp")
    s.add(stream)
    s.flush()
    profile = Profile(
        stream_id=stream.id,
        name="p",
        interval_seconds=60,  # threshold = 180s
        enabled=True,
        auto_disabled=False,
        capture_mode="always",
        created_at=created,
    )
    s.add(profile)
    s.flush()
    s.add(Capture(profile_id=profile.id, file_path="a.jpg", captured_at=captured))
    s.commit()
    s.close()


def test_emits_alert_when_gap_exceeds_threshold():
    from app.services import capture_gap

    Session = _session_factory()
    _seed(Session, last_capture_age=timedelta(hours=2))
    capture_gap._alerted.clear()

    emit_mock = AsyncMock()
    with patch.object(capture_gap, "SessionLocal", Session), patch(
        "app.services.events.emit", emit_mock
    ):
        asyncio.run(capture_gap.check_capture_gaps())

    assert emit_mock.await_count == 1
    assert emit_mock.await_args.args[0] == "capture_gap"


def test_no_alert_when_recent_capture():
    from app.services import capture_gap

    Session = _session_factory()
    _seed(Session, last_capture_age=timedelta(seconds=30))  # < 180s threshold
    capture_gap._alerted.clear()

    emit_mock = AsyncMock()
    with patch.object(capture_gap, "SessionLocal", Session), patch(
        "app.services.events.emit", emit_mock
    ):
        asyncio.run(capture_gap.check_capture_gaps())

    assert emit_mock.await_count == 0
