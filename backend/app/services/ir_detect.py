"""IR (greyscale) frame detection via mean colour chroma.

A camera in IR / night mode renders monochrome frames (R==G==B per pixel),
so the average per-pixel chroma — ``max(R,G,B) - min(R,G,B)`` — collapses to
near zero. Daytime colour footage has clearly higher chroma. The value is
normalised to a 0..100 scale for human-friendly thresholds.
"""

import numpy as np
from PIL import Image

# Frames are downsampled to this width before measurement; chroma is a global
# average so a small sample is plenty and keeps the cost negligible at any
# capture resolution.
_SAMPLE_WIDTH = 256


def mean_chroma(img: Image.Image) -> float:
    """Return the mean per-pixel colour chroma of ``img`` on a 0..100 scale.

    ~0 for a greyscale (IR) frame, tens for colour footage. Accepts any PIL
    image mode (converted to RGB internally).
    """
    rgb = img.convert("RGB")
    width, height = rgb.size
    if width > _SAMPLE_WIDTH:
        new_height = max(1, round(height * _SAMPLE_WIDTH / width))
        rgb = rgb.resize((_SAMPLE_WIDTH, new_height), Image.BILINEAR)

    arr = np.asarray(rgb, dtype=np.int16)  # int16 so max-min cannot underflow
    spread = arr.max(axis=2) - arr.min(axis=2)  # 0..255 per pixel
    return float(spread.mean()) / 255.0 * 100.0
