"""Frame capture service."""

import asyncio
import logging
import os
from datetime import datetime, timedelta

import numpy as np
from PIL import Image

from app.config import decrypt, settings
from app.database import SessionLocal
from app.models import Capture, Profile, Setting

logger = logging.getLogger(__name__)

MAX_CAPTURE_ATTEMPTS = 3
GREEN_PIXEL_THRESHOLD = 0.05  # 5% of total pixels


def _is_frame_corrupt(path: str) -> bool:
    """Detect RTSP green-block corruption in a captured frame.

    Corrupted RTSP frames contain large blocks of pure green pixels
    (RGB ~0,128,0) from incomplete YUV decode data.
    """
    try:
        img = Image.open(path).convert("RGB")
        pixels = np.array(img)
        img.close()
        green_mask = (pixels[:, :, 0] < 10) & (pixels[:, :, 1] >= 120) & (pixels[:, :, 1] <= 140) & (pixels[:, :, 2] < 10)
        ratio = np.count_nonzero(green_mask) / green_mask.size
        if ratio > GREEN_PIXEL_THRESHOLD:
            logger.warning("Frame corruption detected in %s: %.1f%% green pixels", path, ratio * 100)
            return True
        return False
    except Exception:
        logger.exception("Error checking frame corruption for %s", path)
        return False


def _is_within_active_window(profile, db, now: datetime) -> bool:
    """Check if the current time falls within the profile's active capture window."""
    if profile.capture_mode == "always":
        return True

    if profile.capture_mode == "sun":
        try:
            from astral import LocationInfo
            from astral.sun import sun

            lat_row = db.query(Setting).filter(Setting.key == "location_latitude").first()
            lon_row = db.query(Setting).filter(Setting.key == "location_longitude").first()
            if not lat_row or not lon_row:
                return True  # No location configured, allow capture
            lat, lon = float(lat_row.value), float(lon_row.value)
            loc = LocationInfo(latitude=lat, longitude=lon)
            s = sun(loc.observer, date=now.date())
            offset = timedelta(minutes=profile.sun_offset_minutes)
            start = (s["sunrise"] - offset).time()
            end = (s["sunset"] + offset).time()
        except Exception:
            logger.warning("Failed to compute sun times for profile %d, allowing capture", profile.id)
            return True
    else:  # manual
        if not profile.active_start_time or not profile.active_end_time:
            return True
        start = datetime.strptime(profile.active_start_time, "%H:%M").time()
        end = datetime.strptime(profile.active_end_time, "%H:%M").time()

    current = now.time()
    if start <= end:
        return start <= current <= end
    else:  # overnight span
        return current >= start or current <= end


async def capture_frame(profile_id: int) -> None:
    """Capture a single frame for the given profile.

    Runs from the scheduler so creates its own DB session.
    """
    db = SessionLocal()
    try:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        if not profile:
            logger.error("Profile %d not found, skipping capture", profile_id)
            return

        stream = profile.stream
        if not stream:
            logger.error("Stream not found for profile %d", profile_id)
            return

        url = decrypt(stream.url)
        now = datetime.now()

        if not _is_within_active_window(profile, db, now):
            logger.debug("Profile %d outside active window, skipping", profile_id)
            return

        # Build output path
        date_dir = now.strftime("%Y-%m-%d")
        filename = now.strftime("%H-%M-%S") + ".jpg"
        rel_path = os.path.join(
            "captures", str(stream.id), str(profile.id), date_dir, filename
        )
        abs_path = os.path.join(settings.DATA_DIR, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        if profile.hdr_enabled:
            from app.services.hdr import capture_hdr_frame

            valid_frame = False
            for attempt in range(1, MAX_CAPTURE_ATTEMPTS + 1):
                result = await capture_hdr_frame(url, abs_path, quality=profile.quality)
                if _is_frame_corrupt(abs_path):
                    logger.warning(
                        "HDR capture attempt %d/%d corrupt for profile %d",
                        attempt, MAX_CAPTURE_ATTEMPTS, profile_id,
                    )
                    if os.path.exists(abs_path):
                        os.remove(abs_path)
                    continue
                valid_frame = True
                break

            if not valid_frame:
                logger.error(
                    "All %d HDR capture attempts corrupt for profile %d",
                    MAX_CAPTURE_ATTEMPTS, profile_id,
                )
                from app.services.events import emit
                await emit(
                    "capture_failure",
                    f"Capture failed: {profile.name}",
                    f"All {MAX_CAPTURE_ATTEMPTS} capture attempts produced corrupt frames for profile '{profile.name}' on stream '{stream.name}'",
                    level="error",
                )
                return

            width = result["width"]
            height = result["height"]
            file_size = result["file_size"]
            is_hdr = True
        else:
            # Standard single-frame capture via ffmpeg with corruption retry
            valid_frame = False
            for attempt in range(1, MAX_CAPTURE_ATTEMPTS + 1):
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg",
                    "-y",
                    "-rtsp_transport", "tcp",
                    "-i", url,
                    "-frames:v", "1",
                    "-loglevel", "error",
                    "-q:v", "2",
                    abs_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
                if proc.returncode != 0:
                    err_msg = stderr.decode().strip()
                    logger.error(
                        "ffmpeg capture failed for profile %d: %s",
                        profile_id,
                        err_msg,
                    )
                    from app.services.events import emit
                    await emit(
                        "capture_failure",
                        f"Capture failed: {profile.name}",
                        f"ffmpeg error for profile '{profile.name}' on stream '{stream.name}': {err_msg}",
                        level="error",
                    )
                    return

                if _is_frame_corrupt(abs_path):
                    logger.warning(
                        "Capture attempt %d/%d corrupt for profile %d",
                        attempt, MAX_CAPTURE_ATTEMPTS, profile_id,
                    )
                    if os.path.exists(abs_path):
                        os.remove(abs_path)
                    continue
                valid_frame = True
                break

            if not valid_frame:
                logger.error(
                    "All %d capture attempts corrupt for profile %d",
                    MAX_CAPTURE_ATTEMPTS, profile_id,
                )
                from app.services.events import emit
                await emit(
                    "capture_failure",
                    f"Capture failed: {profile.name}",
                    f"All {MAX_CAPTURE_ATTEMPTS} capture attempts produced corrupt frames for profile '{profile.name}' on stream '{stream.name}'",
                    level="error",
                )
                return

            is_hdr = False

            # Resize if configured
            if profile.resolution_width and profile.resolution_height:
                img = Image.open(abs_path)
                img = img.resize(
                    (profile.resolution_width, profile.resolution_height),
                    Image.LANCZOS,
                )
                img.save(abs_path, "JPEG", quality=profile.quality)
                img.close()
            else:
                # Re-save with configured quality
                img = Image.open(abs_path)
                img.save(abs_path, "JPEG", quality=profile.quality)
                img.close()

            # Get dimensions and size
            img = Image.open(abs_path)
            width, height = img.size
            img.close()
            file_size = os.path.getsize(abs_path)

        # Create DB record
        capture = Capture(
            profile_id=profile_id,
            file_path=rel_path,
            file_size=file_size,
            width=width,
            height=height,
            is_hdr=is_hdr,
            captured_at=now,
        )
        db.add(capture)
        db.commit()
        logger.info(
            "Captured frame for profile %d: %s (%dx%d, %d bytes)",
            profile_id, rel_path, width, height, file_size,
        )

    except Exception as exc:
        logger.exception("Capture failed for profile %d", profile_id)
        try:
            from app.services.events import emit
            await emit(
                "capture_failure",
                f"Capture failed: profile {profile_id}",
                f"Unexpected error during capture for profile {profile_id}: {exc}",
                level="error",
            )
        except Exception:
            pass
    finally:
        db.close()
