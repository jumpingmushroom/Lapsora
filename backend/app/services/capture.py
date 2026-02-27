"""Frame capture service."""

import asyncio
import logging
import os
from datetime import datetime

from PIL import Image

from app.config import decrypt, settings
from app.database import SessionLocal
from app.models import Capture, Profile

logger = logging.getLogger(__name__)


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
        now = datetime.utcnow()

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

            result = await capture_hdr_frame(url, abs_path, quality=profile.quality)
            width = result["width"]
            height = result["height"]
            file_size = result["file_size"]
            is_hdr = True
        else:
            # Standard single-frame capture via ffmpeg
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
