"""Timelapse generation service."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Capture, Timelapse
from app.services.deflicker import deflicker_frames

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 300  # 5 minutes


def get_period_range(
    period_type: str, reference_date: datetime | None = None
) -> tuple[datetime, datetime]:
    """Return (start, end) for a named period relative to reference_date."""
    ref = reference_date or datetime.now()

    if period_type == "daily":
        day = ref.date() - timedelta(days=1)
        start = datetime(day.year, day.month, day.day, 0, 0, 0)
        end = datetime(day.year, day.month, day.day, 23, 59, 59)
    elif period_type == "weekly":
        # Last complete Mon-Sun week
        last_sunday = ref.date() - timedelta(days=ref.weekday() + 1)
        last_monday = last_sunday - timedelta(days=6)
        start = datetime(last_monday.year, last_monday.month, last_monday.day, 0, 0, 0)
        end = datetime(last_sunday.year, last_sunday.month, last_sunday.day, 23, 59, 59)
    elif period_type == "monthly":
        first_this_month = ref.date().replace(day=1)
        last_day_prev = first_this_month - timedelta(days=1)
        first_prev = last_day_prev.replace(day=1)
        start = datetime(first_prev.year, first_prev.month, first_prev.day, 0, 0, 0)
        end = datetime(
            last_day_prev.year, last_day_prev.month, last_day_prev.day, 23, 59, 59
        )
    elif period_type == "yearly":
        year = ref.year - 1
        start = datetime(year, 1, 1, 0, 0, 0)
        end = datetime(year, 12, 31, 23, 59, 59)
    else:
        raise ValueError(f"Unknown period_type: {period_type}")

    return start, end


async def generate_timelapse(
    profile_id: int,
    period_type: str = "custom",
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    fps: int = 24,
    format: str = "mp4",
    timestamp_overlay: bool = False,
    weather_overlay: bool = False,
    weather_position: str = "bottom-right",
    weather_font_size: int = 24,
    weather_unit: str = "C",
) -> int:
    """Generate a timelapse video and return its database ID."""
    db: Session = SessionLocal()
    tmp_filelist = None
    deflicker_dir = None
    try:
        # Resolve period bounds
        if period_type != "custom" and (period_start is None or period_end is None):
            period_start, period_end = get_period_range(period_type)
        elif period_start is None or period_end is None:
            # Default custom to last 24 hours
            period_end = datetime.now()
            period_start = period_end - timedelta(hours=24)

        # Query captures
        stmt = (
            select(Capture)
            .where(
                Capture.profile_id == profile_id,
                Capture.captured_at >= period_start,
                Capture.captured_at <= period_end,
            )
            .order_by(Capture.captured_at.asc())
        )
        captures = db.execute(stmt).scalars().all()

        if not captures:
            raise ValueError(
                f"No captures found for profile {profile_id} "
                f"between {period_start} and {period_end}"
            )

        frame_count = len(captures)
        logger.info(
            "Generating %s timelapse for profile %d: %d frames",
            format,
            profile_id,
            frame_count,
        )

        try:
            from app.services.events import emit
            await emit(
                "timelapse_started",
                f"Timelapse generating: {period_type}",
                f"Generating {format} timelapse for profile {profile_id}: {frame_count} frames.",
            )
        except Exception:
            pass

        # Deflicker frames to smooth brightness transitions
        original_paths = [os.path.join(settings.DATA_DIR, cap.file_path) for cap in captures]
        deflicker_dir = tempfile.mkdtemp(prefix="lapsora_deflicker_")
        deflickered_paths = [
            os.path.join(deflicker_dir, f"frame_{i:06d}.jpg")
            for i in range(frame_count)
        ]
        await asyncio.to_thread(deflicker_frames, original_paths, deflickered_paths, 10)
        frame_paths = [p for p in deflickered_paths if os.path.exists(p)]
        if not frame_paths:
            raise ValueError(
                f"No readable frames for profile {profile_id} — "
                f"{len(captures)} captures found but none could be read from disk"
            )

        frame_count = len(frame_paths)

        # Apply weather overlay to deflickered frames
        if weather_overlay:
            from PIL import Image, ImageDraw, ImageFont
            from app.services.weather import format_weather_text

            for i, path in enumerate(frame_paths):
                if i >= len(captures):
                    break
                cap = captures[i]
                if cap.weather_temp is None:
                    continue
                try:
                    img = Image.open(path)
                    draw = ImageDraw.Draw(img)
                    text = format_weather_text(cap.weather_temp, cap.weather_code or 0, weather_unit)
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", weather_font_size)
                    except Exception:
                        font = ImageFont.load_default()
                    bbox = draw.textbbox((0, 0), text, font=font)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    w, h = img.size
                    pad = 10
                    positions = {
                        "top-left": (pad, pad),
                        "top-right": (w - tw - pad, pad),
                        "bottom-left": (pad, h - th - pad),
                        "bottom-right": (w - tw - pad, h - th - pad),
                    }
                    x, y = positions.get(weather_position, positions["bottom-right"])
                    # Draw background box
                    draw.rectangle([x - 5, y - 5, x + tw + 5, y + th + 5], fill=(0, 0, 0, 128))
                    draw.text((x, y), text, font=font, fill="white")
                    img.save(path, "JPEG", quality=95)
                    img.close()
                except Exception:
                    logger.warning("Failed to apply weather overlay to frame %d", i)

        # Write concat file list
        fd, tmp_filelist = tempfile.mkstemp(suffix=".txt", prefix="lapsora_concat_")
        with os.fdopen(fd, "w") as f:
            for path in frame_paths:
                f.write(f"file '{path}'\n")
                f.write(f"duration {1.0 / fps:.6f}\n")
            # Repeat last entry so final frame is shown
            f.write(f"file '{frame_paths[-1]}'\n")

        # Output path
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = format if format != "gif" else "gif"
        out_dir = os.path.join(settings.DATA_DIR, "timelapses", str(profile_id))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{period_type}_{timestamp_str}.{ext}")

        # Build ffmpeg command
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        cmd += ["-f", "concat", "-safe", "0", "-i", tmp_filelist]

        vf_filters: list[str] = []

        if timestamp_overlay:
            vf_filters.append(
                "drawtext=text='%{pts\\:localtime\\:0}'"
                ":fontsize=24:fontcolor=white:x=10:y=10"
                ":box=1:boxcolor=black@0.5:boxborderw=5"
            )

        if format == "mp4":
            cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "23"]
        elif format == "webm":
            cmd += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-crf", "30", "-b:v", "0"]
        elif format == "mkv":
            cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "23"]
        elif format == "gif":
            # GIF needs palette generation filter
            vf_filters.append("split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse")

        if vf_filters:
            cmd += ["-vf", ",".join(vf_filters)]

        cmd.append(out_path)

        # Run ffmpeg
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=FFMPEG_TIMEOUT)

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "unknown error"
            raise RuntimeError(f"ffmpeg failed (rc={proc.returncode}): {error_msg}")

        # Get file size
        file_size = os.path.getsize(out_path)

        # Probe duration with ffprobe
        duration_seconds = None
        try:
            probe_proc = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                out_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            probe_out, _ = await asyncio.wait_for(
                probe_proc.communicate(), timeout=30
            )
            if probe_proc.returncode == 0 and probe_out:
                probe_data = json.loads(probe_out.decode())
                duration_seconds = float(
                    probe_data.get("format", {}).get("duration", 0)
                )
        except Exception:
            logger.warning("ffprobe failed, duration will be estimated")
            duration_seconds = frame_count / fps if fps > 0 else None

        # Create DB record
        timelapse = Timelapse(
            profile_id=profile_id,
            file_path=out_path,
            file_size=file_size,
            format=format,
            fps=fps,
            frame_count=frame_count,
            duration_seconds=duration_seconds,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
        )
        db.add(timelapse)
        db.commit()
        db.refresh(timelapse)

        logger.info(
            "Timelapse %d created: %s (%d bytes, %.1fs)",
            timelapse.id,
            out_path,
            file_size,
            duration_seconds or 0,
        )

        try:
            from app.services.events import emit
            await emit(
                "timelapse_complete",
                f"Timelapse generated: {period_type}",
                f"Timelapse for profile {profile_id} ({period_type}): {frame_count} frames, {duration_seconds or 0:.1f}s duration.",
            )
        except Exception:
            pass

        return timelapse.id

    except Exception as exc:
        logger.exception("Timelapse generation failed for profile %d", profile_id)
        try:
            from app.services.events import emit
            await emit(
                "timelapse_failure",
                f"Timelapse failed: profile {profile_id}",
                f"Timelapse generation failed for profile {profile_id} ({period_type}): {exc}",
                level="error",
            )
        except Exception:
            pass
        raise
    finally:
        db.close()
        if tmp_filelist and os.path.exists(tmp_filelist):
            os.unlink(tmp_filelist)
        if deflicker_dir and os.path.isdir(deflicker_dir):
            shutil.rmtree(deflicker_dir, ignore_errors=True)
