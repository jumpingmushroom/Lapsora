"""Capture gap alerting — detects profiles that stopped receiving frames."""

import logging
from datetime import UTC, datetime

from sqlalchemy import func

from app.database import SessionLocal
from app.models import Capture, Profile, Setting

logger = logging.getLogger(__name__)

# In-memory suppression: profile_id → True when alerted, cleared on successful capture
_alerted: dict[int, bool] = {}


def _as_utc(dt: datetime) -> datetime:
    """Treat a DB-read datetime as UTC. SQLite returns naive datetimes even
    though we store ``datetime.now(UTC)``, so attach UTC before any arithmetic
    against an aware ``now`` (otherwise subtraction raises TypeError)."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def clear_alert(profile_id: int) -> None:
    """Reset alert state after a successful capture."""
    _alerted.pop(profile_id, None)


async def check_capture_gaps() -> None:
    """Check all enabled profiles for capture gaps and emit alerts."""
    db = SessionLocal()
    try:
        # Check if capture gap alerting is enabled
        row = db.query(Setting).filter(Setting.key == "capture_gap_enabled").first()
        if row and row.value == "false":
            return

        profiles = (
            db.query(Profile)
            .filter(Profile.enabled.is_(True), Profile.auto_disabled.is_(False))
            .all()
        )
        now = datetime.now(UTC)

        # One grouped query for every profile's last capture instead of a
        # per-profile MAX() round trip.
        last_by_profile = dict(
            db.query(Capture.profile_id, func.max(Capture.captured_at))
            .group_by(Capture.profile_id)
            .all()
        )

        for profile in profiles:
            try:
                threshold_seconds = profile.interval_seconds * 3

                # Skip profiles with zero captures
                last_capture_at = last_by_profile.get(profile.id)
                if last_capture_at is None:
                    continue

                # Skip recently created profiles
                age = (now - _as_utc(profile.created_at)).total_seconds()
                if age < threshold_seconds:
                    continue

                # Skip if outside active window
                from app.services.capture import _is_within_active_window
                if not _is_within_active_window(profile, db, now):
                    continue

                gap_seconds = (now - _as_utc(last_capture_at)).total_seconds()
                if gap_seconds > threshold_seconds and not _alerted.get(profile.id):
                    gap_minutes = int(gap_seconds / 60)
                    from app.services.events import emit
                    await emit(
                        "capture_gap",
                        f"Capture gap: {profile.name}",
                        f"No frames captured for profile '{profile.name}' in {gap_minutes} minutes "
                        f"(expected every {profile.interval_seconds}s).",
                        level="warning",
                    )
                    _alerted[profile.id] = True

            except Exception:
                logger.exception("Error checking capture gap for profile %d", profile.id)
                continue

    except Exception:
        logger.exception("Capture gap check failed")
    finally:
        db.rollback()
        db.close()
