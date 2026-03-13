"""Stream health monitoring service."""

import json
import logging
from datetime import UTC, datetime

from app.config import decrypt
from app.database import SessionLocal
from app.models import Profile, Setting, Stream
from app.services.events import emit
from app.services.rtsp import test_connection

logger = logging.getLogger(__name__)


def _get_failure_threshold(db) -> int:
    row = db.query(Setting).filter(Setting.key == "health_check_failure_threshold").first()
    if row:
        try:
            return int(row.value)
        except (ValueError, TypeError):
            pass
    return 3


async def check_all_streams() -> None:
    """Check connectivity for all enabled streams and manage profile states."""
    db = SessionLocal()
    try:
        streams = db.query(Stream).filter(Stream.enabled.is_(True)).all()
        threshold = _get_failure_threshold(db)

        for stream in streams:
            try:
                if stream.source_type == "go2rtc":
                    from app.services.go2rtc import get_go2rtc_url, test_stream as go2rtc_test
                    base_url = get_go2rtc_url(db)
                    if not base_url:
                        logger.warning("go2rtc URL not configured, skipping stream %d", stream.id)
                        continue
                    result = await go2rtc_test(base_url, stream.go2rtc_name)
                else:
                    url = decrypt(stream.url)
                    result = await test_connection(url)
                now = datetime.now(UTC)
                stream.last_checked_at = now

                if result["success"]:
                    was_unhealthy = stream.health_status == "unhealthy"
                    stream.consecutive_failures = 0
                    stream.health_status = "healthy"

                    if was_unhealthy:
                        # Re-enable auto-disabled profiles
                        auto_disabled = (
                            db.query(Profile)
                            .filter(
                                Profile.stream_id == stream.id,
                                Profile.auto_disabled.is_(True),
                            )
                            .all()
                        )
                        for profile in auto_disabled:
                            profile.enabled = True
                            profile.auto_disabled = False
                            from app.services.scheduler import add_capture_job
                            add_capture_job(profile)

                        await emit(
                            "stream_recovered",
                            f"Stream recovered: {stream.name}",
                            f"Stream '{stream.name}' is back online. {len(auto_disabled)} profile(s) re-enabled.",
                        )

                else:
                    stream.consecutive_failures += 1

                    if (
                        stream.consecutive_failures >= threshold
                        and stream.health_status != "unhealthy"
                    ):
                        stream.health_status = "unhealthy"

                        # Auto-disable enabled profiles
                        enabled_profiles = (
                            db.query(Profile)
                            .filter(
                                Profile.stream_id == stream.id,
                                Profile.enabled.is_(True),
                            )
                            .all()
                        )
                        for profile in enabled_profiles:
                            profile.enabled = False
                            profile.auto_disabled = True
                            from app.services.scheduler import remove_capture_job
                            remove_capture_job(profile.id)

                        await emit(
                            "stream_unhealthy",
                            f"Stream unhealthy: {stream.name}",
                            f"Stream '{stream.name}' failed {stream.consecutive_failures} consecutive health checks. "
                            f"{len(enabled_profiles)} profile(s) disabled.",
                            level="error",
                        )

                db.commit()

            except Exception:
                logger.exception("Health check failed for stream %d", stream.id)

    finally:
        db.rollback()
        db.close()
