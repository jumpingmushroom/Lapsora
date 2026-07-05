"""Timelapse generation service."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Capture, Timelapse
from app.services.deflicker import deflicker_frames
from app.services.gpu import is_nvenc_available, get_nvenc_encoders, is_cupy_available
from app.services.rtsp import _kill

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class GenerationCancelled(Exception):
    pass

COLORMAP_MAP = {
    "jet": cv2.COLORMAP_JET,
    "inferno": cv2.COLORMAP_INFERNO,
    "viridis": cv2.COLORMAP_VIRIDIS,
    "turbo": cv2.COLORMAP_TURBO,
}

# Output-fps bounds for target-duration rendering. A 3D print's frame count
# varies wildly (short prints -> a few frames, tall prints -> thousands), so
# target_duration mode picks an fps that renders to a consistent length,
# clamped so we never emit a 1-frame-per-second slideshow or a 5000fps blur.
FPS_MIN = 5
FPS_MAX = 60


def _resolve_fps(fps_mode: str, fps: int, render_target_seconds: int, frame_count: int) -> int:
    """Resolve the effective output fps.

    In 'target_duration' mode, compute an fps that renders `frame_count` frames
    to ~`render_target_seconds` seconds, clamped to [FPS_MIN, FPS_MAX]. Any other
    mode (default 'fixed') returns `fps` unchanged. Guards against zero target or
    zero frames by falling back to the provided fps.
    """
    if fps_mode != "target_duration":
        return fps
    if render_target_seconds <= 0 or frame_count <= 0:
        return fps
    computed = round(frame_count / render_target_seconds)
    return max(FPS_MIN, min(FPS_MAX, computed))


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
    """Compute per-frame heatmaps using exponential decay sliding window.

    Returns a list index-aligned with ``frame_paths``: ``heatmaps[i]`` is the
    heatmap for ``frame_paths[i]`` (or ``None`` for the first frame and any
    unreadable frame). Index alignment must hold even when a frame fails to
    decode, otherwise overlays get painted onto the wrong frames.
    """
    heatmaps: list[np.ndarray | None] = [None] * len(frame_paths)
    if len(frame_paths) < 2:
        return heatmaps

    use_gpu = is_cupy_available()
    if use_gpu:
        import cupy as cp
        from cupyx.scipy.ndimage import gaussian_filter as gpu_gaussian_filter

    accumulator = None
    prev_gray = None
    for i, path in enumerate(frame_paths):
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
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
                heatmaps[i] = cp.asnumpy(normalized)
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
                heatmaps[i] = normalized
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
    cancel_check: callable = None,
) -> None:
    """Compute heatmaps and per-pixel alpha-blend them onto frames in-place."""
    colormap = COLORMAP_MAP.get(colormap_name, cv2.COLORMAP_JET)
    use_gpu = is_cupy_available()
    blend = _blend_heatmap_gpu if use_gpu else _blend_heatmap_cpu

    if heatmap_mode == "sliding":
        heatmaps = compute_sliding_heatmaps(frame_paths, threshold=threshold)
        for i, path in enumerate(frame_paths):
            if cancel_check and i % 10 == 0:
                cancel_check()
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
        for i, path in enumerate(frame_paths):
            if cancel_check and i % 10 == 0:
                cancel_check()
            frame = cv2.imread(path)
            if frame is None:
                continue
            blended = blend(frame, colored, heatmap, threshold)
            cv2.imwrite(path, blended, [cv2.IMWRITE_JPEG_QUALITY, 95])

MOTION_BLUR_FRAMES = {"off": 1, "low": 3, "medium": 5, "high": 7}


def apply_motion_blur(frame_dir: str, blend_count: int, cancel_check: callable = None) -> None:
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

    paths = [os.path.join(frame_dir, f) for f in frame_files]
    n = len(paths)

    use_gpu = is_cupy_available()
    if use_gpu:
        import cupy as cp

    # Sliding cache of ORIGINAL decoded frames keyed by index, bounded to the
    # blend window (~blend_count frames) instead of the whole sequence — a few
    # thousand 1080p frames held at once is tens of GB and OOM-kills the app.
    # We overwrite paths[i] with the blended result as we advance, so neighbours
    # must be served from this cache (their on-disk copy is already blended),
    # never re-read from disk.
    cache: dict = {}

    def _load(idx: int):
        if idx not in cache:
            cache[idx] = cv2.imread(paths[idx])  # uint8 or None
        return cache[idx]

    for i in range(n):
        if cancel_check and i % 10 == 0:
            cancel_check()
        # Determine window with boundary clamping
        start = max(0, i - half)
        end = min(n - 1, i + half)
        # Drop originals no future window can reach, then load this window.
        for stale in [k for k in cache if k < start]:
            del cache[stale]
        for j in range(start, end + 1):
            _load(j)
        if cache.get(i) is None:
            continue
        # Gather valid frames and their weights
        w_list = []
        f_list = []
        for j in range(start, end + 1):
            if cache.get(j) is not None:
                w_list.append(weights[j - i + half])
                f_list.append(cache[j])
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

FFMPEG_TIMEOUT = 300  # 5 minutes


def get_period_range(
    period_type: str, reference_date: datetime | None = None
) -> tuple[datetime, datetime]:
    """Return (start, end) for a named period relative to reference_date.

    Bounds are naive datetimes in UTC, matching how ``Capture.captured_at`` is
    stored, so period selection lines up with the data on non-UTC hosts.
    """
    ref = reference_date or datetime.now(UTC)

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


def _remove_partial_output(*paths) -> None:
    """Unlink partial timelapse output left behind when generation fails or is
    cancelled before the DB row is committed — nothing tracks these files, so
    they would otherwise leak (the orphan sweep only works DB→disk)."""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                logger.exception("Failed to remove partial output %s", path)


def _link_print_job(db, print_job_id: int, timelapse_id: int) -> None:
    """Point a print_jobs row at its generated timelapse (no-op if gone)."""
    from app.models import PrintJob
    pj = db.get(PrintJob, print_job_id)
    if pj:
        pj.timelapse_id = timelapse_id
        db.commit()


def _apply_weather_overlay_frames(
    frame_paths, frame_captures, weather_style, weather_position,
    weather_unit, weather_font_size, layout, cancel_check=None,
):
    """Composite the weather overlay onto each frame. CPU/IO-bound (PIL open +
    re-encode per frame) — run via ``asyncio.to_thread`` so it never blocks the
    event loop (a long job otherwise starves capture jobs and the API)."""
    from PIL import Image
    from app.services.weather_overlay import render_frame

    for i, path in enumerate(frame_paths):
        if cancel_check and i % 10 == 0:
            cancel_check()
        cap = frame_captures[i]
        if cap.weather_temp is None:
            continue
        try:
            img = Image.open(path)
            render_frame(
                img, cap, weather_style, weather_position,
                weather_unit, weather_font_size, layout,
            )
            img.save(path, "JPEG", quality=95)
            img.close()
        except Exception:
            logger.warning("Failed to apply weather overlay to frame %d", i)


def _apply_sensor_overlay_frames(
    frame_paths, frame_captures, ha_overlay_position, sensor_layout, cancel_check=None,
):
    """Composite the Home Assistant sensor overlay onto each frame. Run via
    ``asyncio.to_thread`` (see ``_apply_weather_overlay_frames``)."""
    from PIL import Image
    from app.services.sensor_overlay import render_frame as sensor_render_frame

    for i, path in enumerate(frame_paths):
        if cancel_check and i % 10 == 0:
            cancel_check()
        cap = frame_captures[i]
        if not getattr(cap, "sensor_data", None):
            continue
        try:
            img = Image.open(path)
            sensor_render_frame(img, cap, ha_overlay_position, sensor_layout)
            img.save(path, "JPEG", quality=95)
            img.close()
        except Exception:
            logger.warning("Failed to apply sensor overlay to frame %d", i)


def _apply_logo_overlay_frames(frame_paths, logo_layout, cancel_check=None):
    """Composite the logo/watermark onto each frame. Run via
    ``asyncio.to_thread`` (see ``_apply_weather_overlay_frames``)."""
    from PIL import Image
    from app.services.logo_overlay import render_frame as logo_render_frame

    for i, path in enumerate(frame_paths):
        if cancel_check and i % 10 == 0:
            cancel_check()
        try:
            img = Image.open(path)
            logo_render_frame(img, logo_layout)
            img.save(path, "JPEG", quality=95)
            img.close()
        except Exception:
            logger.warning("Failed to apply logo overlay to frame %d", i)


async def generate_timelapse(
    profile_id: int,
    period_type: str = "custom",
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    fps: int = 24,
    fps_mode: str = "fixed",
    render_target_seconds: int = 20,
    format: str = "mp4",
    timestamp_overlay: bool = False,
    weather_overlay: bool = False,
    weather_position: str = "bottom-right",
    weather_font_size: int = 24,
    weather_unit: str = "C",
    weather_style: str = "glass",
    ha_overlay: bool = False,
    ha_overlay_position: str = "top-left",
    deflicker: str = "medium",
    heatmap_overlay: bool = False,
    heatmap_mode: str = "cumulative",
    heatmap_colormap: str = "jet",
    heatmap_threshold: int = 10,
    logo_overlay: bool = False,
    logo_position: str = "bottom-right",
    logo_size: float = 0.12,
    logo_opacity: float = 0.8,
    motion_blur: str = "off",
    codec: str = "auto",
    output_width: int | None = None,
    output_height: int | None = None,
    quality_preset: str = "medium",
    name: str | None = None,
    print_job_id: int | None = None,
    cancel_event: "threading.Event | None" = None,
    generation_id: str | None = None,
) -> int:
    """Generate a timelapse video and return its database ID."""
    from app.services.events import emit
    from app.services.generation_progress import (
        start_generation, update_step, set_frame_count,
        complete_generation, fail_generation,
    )

    from app.services.generation_queue import set_active_ffmpeg_proc

    if generation_id is None:
        generation_id = str(uuid.uuid4())
    db: Session = SessionLocal()
    tmp_filelist = None
    deflicker_dir = None
    out_path = None
    thumb_path = None

    def _check_cancel():
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelled(f"Generation {generation_id} cancelled")

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
            # Default custom to last 24 hours (UTC, matching stored captured_at)
            period_end = datetime.now(UTC).replace(tzinfo=None)
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
        if ha_overlay:
            steps.append({"name": "sensor_overlay", "label": "Applying sensor overlay"})
        if logo_overlay:
            steps.append({"name": "logo_overlay", "label": "Applying logo overlay"})
        steps.append({"name": "encoding", "label": "Encoding video"})
        steps.append({"name": "finalizing", "label": "Finalizing"})

        start_generation(generation_id, profile_id, steps)

        # Step: querying captures
        _check_cancel()
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
        _check_cancel()
        await _progress("deflickering", "in_progress")
        original_paths = [os.path.join(settings.DATA_DIR, cap.file_path) for cap in captures]
        deflicker_dir = tempfile.mkdtemp(prefix="lapsora_deflicker_")
        deflickered_paths = [
            os.path.join(deflicker_dir, f"frame_{i:06d}.jpg")
            for i in range(frame_count)
        ]
        if deflicker == "off":
            import shutil as _shutil

            def _copy_frames() -> None:
                for src, dst in zip(original_paths, deflickered_paths):
                    if os.path.exists(src):
                        _shutil.copy2(src, dst)

            await asyncio.to_thread(_copy_frames)
        else:
            await asyncio.to_thread(deflicker_frames, original_paths, deflickered_paths, deflicker, cancel_check=_check_cancel)
        # Keep each surviving frame paired with its source capture. Filtering
        # frame_paths alone would shift indices relative to `captures` whenever a
        # frame is dropped, mislabelling the per-frame weather overlay below.
        surviving = [
            (cap, p) for cap, p in zip(captures, deflickered_paths) if os.path.exists(p)
        ]
        frame_paths = [p for _, p in surviving]
        frame_captures = [cap for cap, _ in surviving]
        if not frame_paths:
            raise ValueError(
                f"No readable frames for profile {profile_id} — "
                f"{len(captures)} captures found but none could be read from disk"
            )

        frame_count = len(frame_paths)
        set_frame_count(generation_id, frame_count)
        # Resolve target-duration mode now that the true post-deflicker frame
        # count is known; downstream (concat duration, stored Timelapse.fps)
        # all read `fps`.
        fps = _resolve_fps(fps_mode, fps, render_target_seconds, frame_count)
        await _progress("deflickering", "completed")

        # Step: motion blur
        if blur_blend > 1:
            _check_cancel()
            await _progress("motion_blur", "in_progress")
            await asyncio.to_thread(apply_motion_blur, deflicker_dir, blur_blend, cancel_check=_check_cancel)
            await _progress("motion_blur", "completed")

        # Step: heatmap overlay
        if heatmap_overlay:
            _check_cancel()
            await _progress("heatmap_overlay", "in_progress")
            await asyncio.to_thread(
                apply_heatmap_to_frames,
                frame_paths,
                heatmap_mode,
                heatmap_colormap,
                heatmap_threshold,
                cancel_check=_check_cancel,
            )
            await _progress("heatmap_overlay", "completed")

        # Step: weather overlay
        if weather_overlay:
            _check_cancel()
            await _progress("weather_overlay", "in_progress")
            from app.services.weather_overlay import compute_layout

            valid_caps = [c for c in frame_captures if c.weather_temp is not None]
            layout = (
                compute_layout(valid_caps, weather_style, weather_unit, weather_font_size)
                if weather_style != "minimal" and valid_caps
                else None
            )

            await asyncio.to_thread(
                _apply_weather_overlay_frames,
                frame_paths, frame_captures, weather_style, weather_position,
                weather_unit, weather_font_size, layout,
                cancel_check=_check_cancel,
            )
            await _progress("weather_overlay", "completed")

        # Step: Home Assistant sensor overlay
        if ha_overlay:
            _check_cancel()
            await _progress("sensor_overlay", "in_progress")
            from app.services.sensor_overlay import (
                compute_layout as sensor_compute_layout,
            )

            sensor_caps = [c for c in frame_captures if getattr(c, "sensor_data", None)]
            sensor_layout = sensor_compute_layout(sensor_caps) if sensor_caps else None

            if sensor_layout is not None:
                await asyncio.to_thread(
                    _apply_sensor_overlay_frames,
                    frame_paths, frame_captures, ha_overlay_position, sensor_layout,
                    cancel_check=_check_cancel,
                )
            await _progress("sensor_overlay", "completed")

        # Step: logo / watermark overlay (applied last so it sits on top)
        if logo_overlay:
            _check_cancel()
            await _progress("logo_overlay", "in_progress")
            from app.models import Setting
            from app.services.logo_overlay import (
                compute_layout as logo_compute_layout,
            )

            row = db.query(Setting).filter(Setting.key == "logo_file_path").first()
            logo_path = row.value if row else None

            dims = None
            for p in frame_paths:
                probe = cv2.imread(p)
                if probe is not None:
                    dims = (probe.shape[1], probe.shape[0])
                    break

            logo_layout = (
                logo_compute_layout(
                    logo_path, dims[0], dims[1], logo_size, logo_opacity, logo_position
                )
                if logo_path and dims
                else None
            )
            if logo_layout is None:
                logger.warning("Logo overlay enabled but no logo uploaded; skipping")
            else:
                await asyncio.to_thread(
                    _apply_logo_overlay_frames,
                    frame_paths, logo_layout, cancel_check=_check_cancel,
                )
            await _progress("logo_overlay", "completed")

        # Step: encoding
        _check_cancel()
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
        set_active_ffmpeg_proc(proc)
        # Scale the timeout with the frame count: FFMPEG_TIMEOUT is a floor, plus
        # a generous per-frame budget so a large yearly software encode (e.g.
        # libx265 -preset veryslow over tens of thousands of frames) isn't killed
        # mid-encode, while a genuinely hung process is still bounded.
        encode_timeout = max(FFMPEG_TIMEOUT, 60 + frame_count * 2)
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=encode_timeout)
        except asyncio.TimeoutError:
            # Kill the overran encoder so it stops burning CPU/NVENC and growing
            # the partial output while the next job starts — wait_for only
            # cancels the await, not the process.
            await _kill(proc)
            raise RuntimeError(f"ffmpeg encode timed out after {encode_timeout}s")
        finally:
            set_active_ffmpeg_proc(None)

        if proc.returncode != 0:
            # A non-zero return code right after a cancel request means the
            # cancel path killed ffmpeg — surface it as a cancellation, not a
            # failure (otherwise the user sees a spurious "failed" notification).
            _check_cancel()
            error_msg = stderr.decode().strip() if stderr else "unknown error"
            raise RuntimeError(f"ffmpeg failed (rc={proc.returncode}): {error_msg}")

        await _progress("encoding", "completed")

        # Step: finalizing
        await _progress("finalizing", "in_progress")

        # A cancel that lands after the encode finished must still abort before
        # we commit a Timelapse row, or the user sees both a "cancelled" response
        # and a finished timelapse. GenerationCancelled routes to the cleanup path.
        _check_cancel()

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
            try:
                probe_out, _ = await asyncio.wait_for(
                    probe_proc.communicate(), timeout=30
                )
            except asyncio.TimeoutError:
                # wait_for cancels the await, not the child — kill it so a hung
                # ffprobe doesn't leak a process per generation.
                await _kill(probe_proc)
                raise
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
            try:
                await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                await _kill(proc)
                raise
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
            name=name,
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
        try:
            db.commit()
        except Exception:
            # The video/thumbnail are already on disk; if the row can't be
            # written there is nothing tracking them, so remove them rather than
            # leaking a large orphan file.
            db.rollback()
            for orphan in (out_path, thumb_path):
                if orphan and os.path.exists(orphan):
                    try:
                        os.unlink(orphan)
                    except OSError:
                        logger.exception("Failed to remove orphaned output %s", orphan)
            raise
        db.refresh(timelapse)

        if print_job_id is not None:
            _link_print_job(db, print_job_id, timelapse.id)

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
                data={"generation_id": generation_id},
            )
        except Exception:
            logger.exception("Failed to emit timelapse_complete event for generation %s", generation_id)

        return timelapse.id

    except GenerationCancelled:
        logger.info("Timelapse generation cancelled for profile %d", profile_id)
        _remove_partial_output(out_path, thumb_path)
        from app.services.generation_progress import cancel_generation as cancel_progress
        cancel_progress(generation_id)
        try:
            await emit(
                "timelapse_cancelled",
                f"Timelapse cancelled: profile {profile_id}",
                f"Timelapse generation cancelled for profile {profile_id} ({period_type}).",
            )
        except Exception:
            logger.exception("Failed to emit timelapse_cancelled event for generation %s", generation_id)
    except Exception as exc:
        logger.exception("Timelapse generation failed for profile %d", profile_id)
        _remove_partial_output(out_path, thumb_path)
        fail_generation(generation_id, str(exc))
        try:
            await emit(
                "timelapse_failure",
                f"Timelapse failed: profile {profile_id}",
                f"Timelapse generation failed for profile {profile_id} ({period_type}): {exc}",
                level="error",
                data={"generation_id": generation_id},
            )
        except Exception:
            logger.exception("Failed to emit timelapse_failure event for generation %s", generation_id)
        raise
    finally:
        db.close()
        if tmp_filelist and os.path.exists(tmp_filelist):
            os.unlink(tmp_filelist)
        if deflicker_dir and os.path.isdir(deflicker_dir):
            shutil.rmtree(deflicker_dir, ignore_errors=True)
