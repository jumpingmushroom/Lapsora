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

import cv2
import numpy as np

logger = logging.getLogger(__name__)

COLORMAP_MAP = {
    "jet": cv2.COLORMAP_JET,
    "inferno": cv2.COLORMAP_INFERNO,
    "viridis": cv2.COLORMAP_VIRIDIS,
    "turbo": cv2.COLORMAP_TURBO,
}


def compute_cumulative_heatmap(frame_paths: list[str], threshold: int = 10) -> np.ndarray | None:
    """Compute a single cumulative heatmap from consecutive frame diffs."""
    if len(frame_paths) < 2:
        return None
    accumulator = None
    prev_gray = None
    for path in frame_paths:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        if prev_gray is not None:
            diff = cv2.absdiff(prev_gray, img)
            diff[diff < threshold] = 0
            diff = cv2.GaussianBlur(diff.astype(np.float64), (15, 15), 0)
            if accumulator is None:
                accumulator = np.zeros_like(diff)
            accumulator += diff
        prev_gray = img
    if accumulator is None:
        return None
    max_val = accumulator.max()
    if max_val > 0:
        accumulator = (accumulator / max_val * 255).astype(np.uint8)
    else:
        accumulator = accumulator.astype(np.uint8)
    return accumulator


def compute_sliding_heatmaps(frame_paths: list[str], decay: float = 0.9, threshold: int = 10) -> list[np.ndarray | None]:
    """Compute per-frame heatmaps using exponential decay sliding window."""
    heatmaps: list[np.ndarray | None] = [None]  # first frame has no heatmap
    if len(frame_paths) < 2:
        return [None] * len(frame_paths)
    accumulator = None
    prev_gray = None
    for i, path in enumerate(frame_paths):
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            if i > 0:
                heatmaps.append(None)
            prev_gray = None
            continue
        if prev_gray is not None:
            diff = cv2.absdiff(prev_gray, img)
            diff[diff < threshold] = 0
            diff = cv2.GaussianBlur(diff.astype(np.float64), (15, 15), 0)
            if accumulator is None:
                accumulator = np.zeros_like(diff)
            accumulator = accumulator * decay + diff
            normalized = accumulator.copy()
            max_val = normalized.max()
            if max_val > 0:
                normalized = (normalized / max_val * 255).astype(np.uint8)
            else:
                normalized = normalized.astype(np.uint8)
            heatmaps.append(normalized)
        prev_gray = img
    return heatmaps


def apply_heatmap_to_frames(
    frame_paths: list[str],
    heatmap_mode: str,
    colormap_name: str,
    opacity: float,
    threshold: int = 10,
) -> None:
    """Compute heatmaps and alpha-blend them onto frames in-place."""
    colormap = COLORMAP_MAP.get(colormap_name, cv2.COLORMAP_JET)
    opacity = max(0.1, min(0.8, opacity))

    if heatmap_mode == "sliding":
        heatmaps = compute_sliding_heatmaps(frame_paths, threshold=threshold)
        for i, path in enumerate(frame_paths):
            if i >= len(heatmaps) or heatmaps[i] is None:
                continue
            frame = cv2.imread(path)
            if frame is None:
                continue
            colored = cv2.applyColorMap(heatmaps[i], colormap)
            blended = cv2.addWeighted(frame, 1.0, colored, opacity, 0)
            cv2.imwrite(path, blended, [cv2.IMWRITE_JPEG_QUALITY, 95])
    else:
        heatmap = compute_cumulative_heatmap(frame_paths, threshold=threshold)
        if heatmap is None:
            return
        colored = cv2.applyColorMap(heatmap, colormap)
        for path in frame_paths:
            frame = cv2.imread(path)
            if frame is None:
                continue
            blended = cv2.addWeighted(frame, 1.0, colored, opacity, 0)
            cv2.imwrite(path, blended, [cv2.IMWRITE_JPEG_QUALITY, 95])

MOTION_BLUR_FRAMES = {"off": 1, "low": 3, "medium": 5, "high": 7}


def apply_motion_blur(frame_dir: str, blend_count: int) -> None:
    """Blend adjacent frames using gaussian-weighted averaging for motion blur."""
    frame_files = sorted(
        f for f in os.listdir(frame_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )
    if len(frame_files) < 2 or blend_count < 2:
        return

    half = blend_count // 2
    sigma = blend_count / 4.0

    # Pre-compute gaussian weights
    offsets = np.arange(-half, half + 1, dtype=np.float64)
    weights = np.exp(-0.5 * (offsets / sigma) ** 2)

    # Read all frames into memory as float32
    paths = [os.path.join(frame_dir, f) for f in frame_files]
    frames = []
    for p in paths:
        img = cv2.imread(p)
        if img is not None:
            frames.append(img.astype(np.float32))
        else:
            frames.append(None)

    n = len(frames)
    for i in range(n):
        if frames[i] is None:
            continue
        # Determine window with boundary clamping
        start = max(0, i - half)
        end = min(n - 1, i + half)
        # Gather valid frames and their weights
        w_list = []
        f_list = []
        for j in range(start, end + 1):
            if frames[j] is not None:
                w_list.append(weights[j - i + half])
                f_list.append(frames[j])
        if not f_list:
            continue
        # Normalize weights
        w_arr = np.array(w_list, dtype=np.float32)
        w_arr /= w_arr.sum()
        # Weighted average
        blended = np.zeros_like(f_list[0])
        for w, f in zip(w_arr, f_list):
            blended += w * f
        cv2.imwrite(paths[i], blended.astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 85])


QUALITY_CRF = {
    "h264": {"low": 28, "medium": 23, "high": 18, "lossless": 0},
    "h265": {"low": 32, "medium": 28, "high": 22, "lossless": 0},
    "vp9":  {"low": 38, "medium": 30, "high": 24, "lossless": 0},
}

RESOLUTION_PRESETS = {
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
    "4k":    (3840, 2160),
    "8k":    (7680, 4320),
}

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
    deflicker: str = "medium",
    heatmap_overlay: bool = False,
    heatmap_mode: str = "cumulative",
    heatmap_opacity: float = 0.4,
    heatmap_colormap: str = "jet",
    heatmap_threshold: int = 10,
    motion_blur: str = "off",
    codec: str = "auto",
    output_width: int | None = None,
    output_height: int | None = None,
    quality_preset: str = "medium",
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
        if deflicker == "off":
            # Copy frames without deflickering
            import shutil as _shutil
            for src, dst in zip(original_paths, deflickered_paths):
                if os.path.exists(src):
                    _shutil.copy2(src, dst)
        else:
            await asyncio.to_thread(deflicker_frames, original_paths, deflickered_paths, deflicker)
        frame_paths = [p for p in deflickered_paths if os.path.exists(p)]
        if not frame_paths:
            raise ValueError(
                f"No readable frames for profile {profile_id} — "
                f"{len(captures)} captures found but none could be read from disk"
            )

        frame_count = len(frame_paths)

        # Apply motion blur to smooth frame transitions
        blur_blend = MOTION_BLUR_FRAMES.get(motion_blur, 1)
        if blur_blend > 1:
            await asyncio.to_thread(apply_motion_blur, deflicker_dir, blur_blend)

        # Apply heatmap overlay to deflickered frames
        if heatmap_overlay:
            await asyncio.to_thread(
                apply_heatmap_to_frames,
                frame_paths,
                heatmap_mode,
                heatmap_colormap,
                heatmap_opacity,
                heatmap_threshold,
            )

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

        # Resolution scaling
        if output_width and output_height and format != "gif":
            vf_filters.append(
                f"scale={output_width}:{output_height}:force_original_aspect_ratio=decrease,"
                f"pad={output_width}:{output_height}:(ow-iw)/2:(oh-ih)/2"
            )

        if timestamp_overlay:
            vf_filters.append(
                "drawtext=text='%{pts\\:localtime\\:0}'"
                ":fontsize=24:fontcolor=white:x=10:y=10"
                ":box=1:boxcolor=black@0.5:boxborderw=5"
            )

        if format == "gif":
            # GIF ignores codec/quality_preset
            vf_filters.append("split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse")
        elif format == "webm":
            # WebM always uses VP9 regardless of codec setting
            effective_codec = "vp9"
            crf = QUALITY_CRF["vp9"].get(quality_preset, 30)
            cmd += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-crf", str(crf), "-b:v", "0"]
            if quality_preset == "lossless":
                cmd += ["-lossless", "1"]
        else:
            # MP4 or MKV
            if codec == "h265":
                effective_codec = "h265"
                crf = QUALITY_CRF["h265"].get(quality_preset, 28)
                cmd += ["-c:v", "libx265", "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-crf", str(crf)]
                if quality_preset == "lossless":
                    cmd += ["-preset", "veryslow"]
                else:
                    cmd += ["-preset", "medium"]
            else:
                # auto or h264
                effective_codec = "h264"
                crf = QUALITY_CRF["h264"].get(quality_preset, 23)
                cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf)]
                if quality_preset == "lossless":
                    cmd += ["-preset", "veryslow"]
                else:
                    cmd += ["-preset", "medium"]

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
