"""HDR capture via exposure fusion."""

import asyncio
import logging
import os
import shutil
import tempfile

import cv2
import numpy as np

logger = logging.getLogger(__name__)


async def capture_hdr_frame(url: str, output_path: str, quality: int = 85) -> dict:
    """Capture multiple frames and merge via Mertens exposure fusion.

    1. Grab 3 sequential frames from the RTSP stream.
    2. Apply synthetic exposure bracketing (gamma 0.5, 1.0, 2.0).
    3. Merge with createMergeMertens().
    4. Apply gray-world white balance.
    5. Save as JPEG.

    Returns dict with width, height, file_size.
    """
    tmp_dir = tempfile.mkdtemp()
    frame_paths = []

    try:
        # Grab 3 sequential frames in a single FFmpeg call
        frame_pattern = os.path.join(tmp_dir, "frame_%d.jpg")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-rtsp_transport", "tcp",
            "-skip_frame", "nokey",
            "-i", url,
            "-frames:v", "3",
            "-vsync", "vfr",
            "-loglevel", "error",
            "-q:v", "2",
            frame_pattern,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg frame grab failed: {stderr.decode().strip()}")

        # FFmpeg %d pattern is 1-indexed
        frame_paths = [os.path.join(tmp_dir, f"frame_{i}.jpg") for i in range(1, 4)]

        # Read frames with OpenCV
        frames = []
        for fp in frame_paths:
            img = cv2.imread(fp)
            if img is None:
                raise RuntimeError(f"Failed to read frame: {fp}")
            frames.append(img)

        # Average frames for noise reduction
        base_frame = np.mean(frames, axis=0).astype(np.uint8)

        # Synthetic exposure bracketing via gamma correction
        bracketed = []
        for gamma in (0.5, 1.0, 2.0):
            inv_gamma = 1.0 / gamma
            table = np.array(
                [((i / 255.0) ** inv_gamma) * 255 for i in range(256)]
            ).astype("uint8")
            # Use the averaged frame as base for bracketing
            adjusted = cv2.LUT(base_frame, table)
            bracketed.append(adjusted)

        # Mertens exposure fusion
        merge = cv2.createMergeMertens()
        fusion = merge.process(bracketed)

        # Scale to 0-255 range
        fusion = np.clip(fusion * 255, 0, 255).astype(np.uint8)

        # Gray-world white balance
        b, g, r = cv2.split(fusion)
        overall_mean = np.mean(fusion)
        b_mean = np.mean(b) or 1.0
        g_mean = np.mean(g) or 1.0
        r_mean = np.mean(r) or 1.0
        b = np.clip(b * (overall_mean / b_mean), 0, 255).astype(np.uint8)
        g = np.clip(g * (overall_mean / g_mean), 0, 255).astype(np.uint8)
        r = np.clip(r * (overall_mean / r_mean), 0, 255).astype(np.uint8)
        fusion = cv2.merge([b, g, r])

        # Save
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        cv2.imwrite(output_path, fusion, encode_params)

        height, width = fusion.shape[:2]
        file_size = os.path.getsize(output_path)

        return {"width": width, "height": height, "file_size": file_size}

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
