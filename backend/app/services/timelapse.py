"""Timelapse generation service."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Capture, Timelapse
from app.services.deflicker import deflicker_frames
from app.services.gpu import is_nvenc_available, get_nvenc_encoders, is_cupy_available

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

    use_gpu = is_cupy_available()
    if use_gpu:
        import cupy as cp
        from cupyx.scipy.ndimage import gaussian_filter as gpu_gaussian_filter

    accumulator = None
    prev_gray = None
    for path in frame_paths:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        if prev_gray is not None:
            if use_gpu:
                gpu_curr = cp.asarray(img, dtype=cp.float32)
                gpu_prev = cp.asarray(prev_gray, dtype=cp.float32)
                diff = cp.abs(gpu_curr - gpu_prev)
                diff[diff < threshold] = 0
                diff = gpu_gaussian_filter(diff, sigma=2.6)
                if accumulator is None:
                    accumulator = cp.zeros_like(diff)
                accumulator += diff
            else:
                diff = cv2.absdiff(prev_gray, img)
                diff[diff < threshold] = 0
                diff = cv2.GaussianBlur(diff.astype(np.float32), (15, 15), 0)
                if accumulator is None:
                    accumulator = np.zeros_like(diff)
                accumulator += diff
        prev_gray = img
    if accumulator is None:
        return None

    if use_gpu:
        max_val = float(cp.max(accumulator))
        if max_val > 0:
            result = cp.asnumpy((accumulator / max_val * 255).astype(cp.uint8))
        else:
            result = cp.asnumpy(accumulator.astype(cp.uint8))
        return result

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

    use_gpu = is_cupy_available()
    if use_gpu:
        import cupy as cp
        from cupyx.scipy.ndimage import gaussian_filter as gpu_gaussian_filter

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
            if use_gpu:
                gpu_curr = cp.asarray(img, dtype=cp.float32)
                gpu_prev = cp.asarray(prev_gray, dtype=cp.float32)
                diff = cp.abs(gpu_curr - gpu_prev)
                diff[diff < threshold] = 0
                diff = gpu_gaussian_filter(diff, sigma=2.6)
                if accumulator is None:
                    accumulator = cp.zeros_like(diff)
                accumulator = accumulator * decay + diff
                normalized = accumulator.copy()
                max_val = float(cp.max(normalized))
                if max_val > 0:
                    normalized = (normalized / max_val * 255).astype(cp.uint8)
                else:
                    normalized = normalized.astype(cp.uint8)
                heatmaps.append(cp.asnumpy(normalized))
            else:
                diff = cv2.absdiff(prev_gray, img)
                diff[diff < threshold] = 0
                diff = cv2.GaussianBlur(diff.astype(np.float32), (15, 15), 0)
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


def _blend_heatmap_gpu(frame: np.ndarray, colored: np.ndarray, heatmap: np.ndarray, threshold: int) -> np.ndarray:
    """Per-pixel alpha blend a colored heatmap onto a frame using CuPy."""
    import cupy as cp
    gpu_frame = cp.asarray(frame, dtype=cp.float32)
    gpu_colored = cp.asarray(colored, dtype=cp.float32)
    alpha = cp.asarray(heatmap, dtype=cp.float32) / 255.0
    alpha[cp.asarray(heatmap) < threshold] = 0
    alpha = cp.asnumpy(alpha)
    alpha = cv2.GaussianBlur(alpha, (31, 31), 0)
    alpha_3ch = cp.asarray(np.stack([alpha] * 3, axis=-1))
    blended = gpu_frame * (1 - alpha_3ch) + gpu_colored * alpha_3ch
    return cp.asnumpy(cp.clip(blended, 0, 255).astype(cp.uint8))


def _blend_heatmap_cpu(frame: np.ndarray, colored: np.ndarray, heatmap: np.ndarray, threshold: int) -> np.ndarray:
    """Per-pixel alpha blend a colored heatmap onto a frame using NumPy."""
    alpha = heatmap.astype(np.float32) / 255.0
    alpha[heatmap < threshold] = 0
    alpha = cv2.GaussianBlur(alpha, (31, 31), 0)
    alpha_3ch = np.stack([alpha] * 3, axis=-1)
    blended = frame.astype(np.float32) * (1 - alpha_3ch) + colored.astype(np.float32) * alpha_3ch
    return np.clip(blended, 0, 255).astype(np.uint8)


def apply_heatmap_to_frames(
    frame_paths: list[str],
    heatmap_mode: str,
    colormap_name: str,
    threshold: int = 10,
) -> None:
    """Compute heatmaps and per-pixel alpha-blend them onto frames in-place."""
    colormap = COLORMAP_MAP.get(colormap_name, cv2.COLORMAP_JET)
    use_gpu = is_cupy_available()
    blend = _blend_heatmap_gpu if use_gpu else _blend_heatmap_cpu

    if heatmap_mode == "sliding":
        heatmaps = compute_sliding_heatmaps(frame_paths, threshold=threshold)
        for i, path in enumerate(frame_paths):
            if i >= len(heatmaps) or heatmaps[i] is None:
                continue
            frame = cv2.imread(path)
            if frame is None:
                continue
            colored = cv2.applyColorMap(heatmaps[i], colormap)
            blended = blend(frame, colored, heatmaps[i], threshold)
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
            blended = blend(frame, colored, heatmap, threshold)
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
    offsets = np.arange(-half, half + 1, dtype=np.float32)
    weights = np.exp(-0.5 * (offsets / sigma) ** 2)

    # Read all frames into memory as uint8 (convert to float only in blend window)
    paths = [os.path.join(frame_dir, f) for f in frame_files]
    frames = []
    for p in paths:
        img = cv2.imread(p)
        frames.append(img)  # keep as uint8 or None

    use_gpu = is_cupy_available()
    if use_gpu:
        import cupy as cp

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

        if use_gpu:
            w_arr = cp.array(w_list, dtype=cp.float32)
            w_arr /= w_arr.sum()
            gpu_frames = [cp.asarray(f, dtype=cp.float32) for f in f_list]
            blended = cp.zeros_like(gpu_frames[0])
            for w, f in zip(w_arr, gpu_frames):
                blended += w * f
            result = cp.asnumpy(blended.astype(cp.uint8))
        else:
            w_arr = np.array(w_list, dtype=np.float32)
            w_arr /= w_arr.sum()
            blended = np.zeros_like(f_list[0], dtype=np.float32)
            for w, f in zip(w_arr, f_list):
                blended += w * f.astype(np.float32)
            result = blended.astype(np.uint8)

        cv2.imwrite(paths[i], result, [cv2.IMWRITE_JPEG_QUALITY, 85])


QUALITY_CRF = {
    "h264": {"low": 28, "medium": 23, "high": 18, "lossless": 0},
    "h265": {"low": 32, "medium": 28, "high": 22, "lossless": 0},
    "vp9":  {"low": 38, "medium": 30, "high": 24, "lossless": 0},
}

# NVENC uses -cq (constant quality) instead of -crf
NVENC_QUALITY_CQ = {
    "h264": {"low": 32, "medium": 26, "high": 20},
    "h265": {"low": 36, "medium": 30, "high": 24},
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
    heatmap_colormap: str = "jet",
    heatmap_threshold: int = 10,
    motion_blur: str = "off",
    codec: str = "auto",
    output_width: int | None = None,
    output_height: int | None = None,
    quality_preset: str = "medium",
) -> int:
    """Generate a timelapse video and return its database ID."""
    from app.services.events import emit
    from app.services.generation_progress import (
        start_generation, update_step, set_frame_count,
        complete_generation, fail_generation,
    )

    generation_id = str(uuid.uuid4())
    db: Session = SessionLocal()
    tmp_filelist = None
    deflicker_dir = None

    async def _progress(step_name: str, status: str) -> None:
        """Update step and emit SSE progress event."""
        state = update_step(generation_id, step_name, status)
        if state:
            await emit("timelapse_progress", "", "", data=state)

    try:
        # Resolve period bounds
        if period_type != "custom" and (period_start is None or period_end is None):
            period_start, period_end = get_period_range(period_type)
        elif period_start is None or period_end is None:
            # Default custom to last 24 hours
            period_end = datetime.now()
            period_start = period_end - timedelta(hours=24)

        # Build dynamic step list based on options
        steps: list[dict] = [{"name": "querying_captures", "label": "Querying captures"}]
        steps.append({"name": "deflickering", "label": "Deflickering frames" if deflicker != "off" else "Copying frames"})
        blur_blend = MOTION_BLUR_FRAMES.get(motion_blur, 1)
        if blur_blend > 1:
            steps.append({"name": "motion_blur", "label": "Applying motion blur"})
        if heatmap_overlay:
            steps.append({"name": "heatmap_overlay", "label": "Applying heatmap overlay"})
        if weather_overlay:
            steps.append({"name": "weather_overlay", "label": "Applying weather overlay"})
        steps.append({"name": "encoding", "label": "Encoding video"})
        steps.append({"name": "finalizing", "label": "Finalizing"})

        start_generation(generation_id, profile_id, steps)

        # Step: querying captures
        await _progress("querying_captures", "in_progress")

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
        set_frame_count(generation_id, frame_count)
        logger.info(
            "Generating %s timelapse for profile %d: %d frames",
            format,
            profile_id,
            frame_count,
        )

        await _progress("querying_captures", "completed")

        try:
            await emit(
                "timelapse_started",
                f"Timelapse generating: {period_type}",
                f"Generating {format} timelapse for profile {profile_id}: {frame_count} frames.",
            )
        except Exception:
            pass

        # Step: deflickering / copying frames
        await _progress("deflickering", "in_progress")
        original_paths = [os.path.join(settings.DATA_DIR, cap.file_path) for cap in captures]
        deflicker_dir = tempfile.mkdtemp(prefix="lapsora_deflicker_")
        deflickered_paths = [
            os.path.join(deflicker_dir, f"frame_{i:06d}.jpg")
            for i in range(frame_count)
        ]
        if deflicker == "off":
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
        set_frame_count(generation_id, frame_count)
        await _progress("deflickering", "completed")

        # Step: motion blur
        if blur_blend > 1:
            await _progress("motion_blur", "in_progress")
            await asyncio.to_thread(apply_motion_blur, deflicker_dir, blur_blend)
            await _progress("motion_blur", "completed")

        # Step: heatmap overlay
        if heatmap_overlay:
            await _progress("heatmap_overlay", "in_progress")
            await asyncio.to_thread(
                apply_heatmap_to_frames,
                frame_paths,
                heatmap_mode,
                heatmap_colormap,
                heatmap_threshold,
            )
            await _progress("heatmap_overlay", "completed")

        # Step: weather overlay
        if weather_overlay:
            await _progress("weather_overlay", "in_progress")
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
            await _progress("weather_overlay", "completed")

        # Step: encoding
        await _progress("encoding", "in_progress")

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

        # Detect source frame dimensions and clamp output resolution
        source_w, source_h = None, None
        for p in frame_paths:
            probe = cv2.imread(p)
            if probe is not None:
                source_h, source_w = probe.shape[:2]
                break

        if output_width and output_height and source_w and source_h:
            if output_width > source_w or output_height > source_h:
                output_width = min(output_width, source_w)
                output_height = min(output_height, source_h)
            if output_width == source_w and output_height == source_h:
                output_width = None
                output_height = None

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
            # WebM always uses VP9 regardless of codec setting (no NVENC equivalent)
            effective_codec = "vp9"
            crf = QUALITY_CRF["vp9"].get(quality_preset, 30)
            cmd += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-crf", str(crf), "-b:v", "0"]
            if quality_preset == "lossless":
                cmd += ["-lossless", "1"]
        else:
            # MP4 or MKV — use NVENC if available, otherwise software encoding
            use_nvenc = is_nvenc_available()
            nvenc_encoders = get_nvenc_encoders() if use_nvenc else {}

            if codec == "h265":
                effective_codec = "h265"
                if use_nvenc and "h265" in nvenc_encoders:
                    logger.info("Using NVENC encoder: hevc_nvenc")
                    cmd += ["-c:v", "hevc_nvenc", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]
                    if quality_preset == "lossless":
                        cmd += ["-tune", "lossless", "-preset", "p4"]
                    else:
                        cq = NVENC_QUALITY_CQ["h265"].get(quality_preset, 30)
                        cmd += ["-cq", str(cq), "-preset", "p4"]
                else:
                    crf = QUALITY_CRF["h265"].get(quality_preset, 28)
                    cmd += ["-c:v", "libx265", "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-crf", str(crf)]
                    if quality_preset == "lossless":
                        cmd += ["-preset", "veryslow"]
                    else:
                        cmd += ["-preset", "medium"]
            else:
                # auto or h264
                effective_codec = "h264"
                if use_nvenc and "h264" in nvenc_encoders:
                    logger.info("Using NVENC encoder: h264_nvenc")
                    cmd += ["-c:v", "h264_nvenc", "-pix_fmt", "yuv420p"]
                    if quality_preset == "lossless":
                        cmd += ["-tune", "lossless", "-preset", "p4"]
                    else:
                        cq = NVENC_QUALITY_CQ["h264"].get(quality_preset, 26)
                        cmd += ["-cq", str(cq), "-preset", "p4"]
                else:
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

        await _progress("encoding", "completed")

        # Step: finalizing
        await _progress("finalizing", "in_progress")

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

        # Extract middle frame as thumbnail
        thumb_path = out_path.rsplit(".", 1)[0] + "_thumb.jpg"
        mid = (duration_seconds or 1) / 2
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-ss", str(mid), "-i", out_path,
                "-frames:v", "1", "-q:v", "2", thumb_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                thumb_path = None
        except Exception:
            logger.warning("Thumbnail extraction failed")
            thumb_path = None

        # Create DB record
        timelapse = Timelapse(
            profile_id=profile_id,
            file_path=out_path,
            thumbnail_path=thumb_path,
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

        await _progress("finalizing", "completed")
        complete_generation(generation_id)

        try:
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
        fail_generation(generation_id, str(exc))
        try:
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
