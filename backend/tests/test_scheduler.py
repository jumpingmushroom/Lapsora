"""Scheduler start-date computation and job-restore resilience.

These cover scheduling logic that previously had no tests, without starting a
real APScheduler (the restore test mocks the add_*_job calls).
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Profile, Stream
from app.services import scheduler


# A fixed midday reference so building "2h earlier/later" never wraps across a
# day boundary (the wall-clock version failed between 00:00-02:00 / 22:00-00:00).
NOW = datetime(2026, 7, 5, 12, 0, 0)


def test_compute_start_date_interval_is_future_and_aligned():
    profile = SimpleNamespace(capture_mode="always", interval_seconds=300, active_start_time=None)
    start = scheduler._compute_start_date(profile, now=NOW)

    # Strictly in the future, within one interval.
    delta = (start - NOW).total_seconds()
    assert 0 < delta <= 300
    # Aligned to an interval boundary measured from the top of the hour.
    top_of_hour = start.replace(minute=0, second=0, microsecond=0)
    assert (start - top_of_hour).total_seconds() % 300 == 0


def test_compute_start_date_manual_future_time_today():
    # A start time later today should schedule for today at that time.
    future = (NOW + timedelta(hours=2)).strftime("%H:%M")
    profile = SimpleNamespace(capture_mode="manual", interval_seconds=60, active_start_time=future)
    start = scheduler._compute_start_date(profile, now=NOW)
    h, m = map(int, future.split(":"))
    assert (start.hour, start.minute) == (h, m)
    assert start >= NOW


def test_compute_start_date_manual_inside_window_resumes_same_day():
    # A start time that already passed (e.g. app restarted mid-window) must
    # resume at the next interval tick today, NOT defer until tomorrow.
    past = (NOW - timedelta(hours=2)).strftime("%H:%M")
    profile = SimpleNamespace(capture_mode="manual", interval_seconds=600, active_start_time=past)
    start = scheduler._compute_start_date(profile, now=NOW)
    # Strictly future, and within one interval — not a ~22h jump to tomorrow.
    assert NOW < start <= NOW + timedelta(seconds=600)


def test_compute_start_date_manual_ticks_aligned_to_anchor():
    # Ticks stay aligned to the window-open anchor + k*interval.
    past = (NOW - timedelta(hours=2)).strftime("%H:%M")
    profile = SimpleNamespace(capture_mode="manual", interval_seconds=600, active_start_time=past)
    h, m = map(int, past.split(":"))
    anchor = NOW.replace(hour=h, minute=m, second=0, microsecond=0)
    start = scheduler._compute_start_date(profile, now=NOW)
    assert (start - anchor).total_seconds() % 600 == 0


def _seed(TestSession, *, enabled_count, disabled_count):
    db = TestSession()
    s = Stream(name="S", url="enc")
    db.add(s)
    db.commit()
    db.refresh(s)
    for i in range(enabled_count):
        db.add(Profile(stream_id=s.id, name=f"on{i}", enabled=True))
    for i in range(disabled_count):
        db.add(Profile(stream_id=s.id, name=f"off{i}", enabled=False))
    db.commit()
    return db


def test_restore_jobs_only_enabled_profiles():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    db = _seed(TestSession, enabled_count=2, disabled_count=1)

    with patch.object(scheduler, "add_capture_job") as add_cap, patch.object(
        scheduler, "add_timelapse_schedule_job"
    ), patch.object(scheduler, "add_cleanup_schedule_job"):
        scheduler.restore_jobs(db)

    assert add_cap.call_count == 2  # disabled profile skipped
    db.close()


def test_restore_jobs_continues_past_a_failing_profile():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    db = _seed(TestSession, enabled_count=3, disabled_count=0)

    # First add_capture_job call raises; restore must log and continue, not abort.
    with patch.object(
        scheduler, "add_capture_job", side_effect=[RuntimeError("boom"), None, None]
    ) as add_cap, patch.object(scheduler, "add_timelapse_schedule_job"), patch.object(
        scheduler, "add_cleanup_schedule_job"
    ):
        scheduler.restore_jobs(db)  # must not raise

    assert add_cap.call_count == 3  # all three attempted despite the first failing
    db.close()
