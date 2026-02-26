"""Timelapse generation service."""

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Capture, Timelapse

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 300  # 5 minutes


def get_period_range(
    period_type: str, reference_date: datetime | None = None
) -> tuple[datetime, datetime]:
    """Return (start, end) for a named period relative to reference_date."""
    ref = reference_date or datetime.utcnow()

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
) -> int:
    """Generate a timelapse video and return its database ID."""
    db: Session = SessionLocal()
    tmp_filelist = None
    try:
        # Resolve period bounds
        if period_type != "custom" and (period_start is None or period_end is None):
            period_start, period_end = get_period_range(period_type)
        elif period_start is None or period_end is None:
            # Default custom to last 24 hours
            period_end = datetime.utcnow()
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

        # Write concat file list
        fd, tmp_filelist = tempfile.mkstemp(suffix=".txt", prefix="lapsora_concat_")
        with os.fdopen(fd, "w") as f:
            for cap in captures:
                # Each frame shown for 1/fps seconds via duration directive
                f.write(f"file '{cap.file_path}'\n")
                f.write(f"duration {1.0 / fps:.6f}\n")
            # Repeat last entry so final frame is shown
            f.write(f"file '{captures[-1].file_path}'\n")

        # Output path
        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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
        return timelapse.id

    finally:
        db.close()
        if tmp_filelist and os.path.exists(tmp_filelist):
            os.unlink(tmp_filelist)
