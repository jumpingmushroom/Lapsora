"""Brightness deflicker for timelapse frame sequences."""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def calc_brightness(image: np.ndarray, sigma: float | None = 2.5) -> float:
    """Calculate mean brightness of an image, with optional sigma clipping."""
    if sigma is not None:
        mask = np.ones(image.shape[:2], dtype=bool)
        for c in range(image.shape[2]):
            channel = image[:, :, c].astype(np.float64)
            mean = channel.mean()
            std = channel.std()
            if std > 0:
                mask &= np.abs(channel - mean) / std <= sigma
        return float(np.mean(image[mask]))
    return float(np.mean(image))


def rolling_mean(data: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean, leaving edges as original values."""
    if window <= 1 or len(data) <= window:
        return data.copy()
    kernel = np.ones(window) / window
    return np.convolve(data, kernel, mode="same")


def deflicker_frames(
    frame_paths: list[str],
    output_paths: list[str],
    window: int = 10,
    sigma: float | None = 2.5,
    quality: int = 85,
) -> None:
    """Deflicker a sequence of frames by matching brightness to a rolling mean.

    Reads frames from frame_paths, adjusts brightness, writes to output_paths.
    If frame count <= 2, copies frames unchanged (rolling mean needs >=3).
    """
    n = len(frame_paths)
    if n <= 2:
        for src, dst in zip(frame_paths, output_paths):
            if src != dst:
                img = cv2.imread(src)
                if img is None:
                    logger.warning("Skipping unreadable frame: %s", src)
                    continue
                cv2.imwrite(dst, img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return

    # Pass 1: compute brightness of each frame, skipping unreadable ones
    brightness = np.empty(n, dtype=np.float64)
    readable = [False] * n
    for i, path in enumerate(frame_paths):
        img = cv2.imread(path)
        if img is None:
            logger.warning("Skipping unreadable frame: %s", path)
            brightness[i] = 0.0
            continue
        readable[i] = True
        brightness[i] = calc_brightness(img, sigma=sigma)

    if not any(readable):
        logger.warning("No readable frames to deflicker")
        return

    # Compute target brightness via rolling mean
    target = rolling_mean(brightness, window)

    # Pass 2: scale each frame and write
    for i, (src, dst) in enumerate(zip(frame_paths, output_paths)):
        if not readable[i]:
            continue
        img = cv2.imread(src)
        if img is None:
            continue
        if brightness[i] > 0:
            scale = target[i] / brightness[i]
            img = np.clip(img.astype(np.float64) * scale, 0, 255).astype(np.uint8)
        cv2.imwrite(dst, img, [cv2.IMWRITE_JPEG_QUALITY, quality])

    logger.info("Deflickered %d frames (window=%d)", n, window)
