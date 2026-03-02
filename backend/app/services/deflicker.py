"""Brightness deflicker for timelapse frame sequences."""

import logging

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

logger = logging.getLogger(__name__)

STRENGTH_SIGMA = {
    "light": 3,
    "medium": 8,
    "heavy": 25,
}


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


def deflicker_frames(
    frame_paths: list[str],
    output_paths: list[str],
    strength: str = "medium",
    sigma: float | None = 2.5,
    quality: int = 85,
) -> None:
    """Deflicker a sequence of frames by matching brightness to a smoothed curve.

    Uses Gaussian smoothing in LAB colorspace to prevent color shifts.
    strength: "light", "medium", or "heavy" (maps to Gaussian sigma).
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

    gauss_sigma = STRENGTH_SIGMA.get(strength, STRENGTH_SIGMA["medium"])

    # Pass 1: compute brightness of each frame
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

    # Compute target brightness via Gaussian smoothing (nearest mode avoids zero-padding)
    target = gaussian_filter1d(brightness, sigma=gauss_sigma, mode="nearest")

    # Pass 2: scale each frame in LAB colorspace and write
    for i, (src, dst) in enumerate(zip(frame_paths, output_paths)):
        if not readable[i]:
            continue
        img = cv2.imread(src)
        if img is None:
            continue
        if brightness[i] > 0:
            scale = target[i] / brightness[i]
            # Scale in LAB colorspace to avoid color shifts
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float64)
            lab[:, :, 0] = np.clip(lab[:, :, 0] * scale, 0, 255)
            img = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
        cv2.imwrite(dst, img, [cv2.IMWRITE_JPEG_QUALITY, quality])

    logger.info("Deflickered %d frames (strength=%s, sigma=%d)", n, strength, gauss_sigma)
