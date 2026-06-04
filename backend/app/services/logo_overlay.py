"""Logo / watermark overlay baked onto timelapse frames.

A single global logo (uploaded in settings) is composited onto each frame at a
chosen corner, sized as a fraction of the frame width and at a chosen opacity.
The prepared logo (resized + alpha-scaled) and its anchor are computed once per
render in compute_layout(); render_frame() just pastes it onto every frame.
"""

import logging
import os

from PIL import Image

logger = logging.getLogger(__name__)

MARGIN_PCT = 0.025  # distance from the frame edge, as a fraction of frame width


def _resize_logo(logo: Image.Image, target_w: int) -> Image.Image:
    w, h = logo.size
    if w <= 0:
        return logo
    target_h = max(1, round(h * target_w / w))
    return logo.resize((target_w, target_h), Image.LANCZOS)


def _apply_opacity(logo: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 1.0:
        return logo
    opacity = max(0.0, min(1.0, opacity))
    alpha = logo.getchannel("A").point(lambda v: int(v * opacity))
    logo.putalpha(alpha)
    return logo


def _anchor(position: str, W: int, H: int, cw: int, ch: int, margin: int) -> tuple[int, int]:
    if position == "top-left":
        x, y = margin, margin
    elif position == "top-right":
        x, y = W - cw - margin, margin
    elif position == "bottom-left":
        x, y = margin, H - ch - margin
    else:  # bottom-right default
        x, y = W - cw - margin, H - ch - margin
    return max(0, x), max(0, y)


def compute_layout(
    logo_path: str | None,
    frame_w: int,
    frame_h: int,
    size_pct: float,
    opacity: float,
    position: str,
) -> dict | None:
    """Prepare the logo once for the whole render.

    Returns a dict consumed by render_frame, or None if no usable logo exists.
    """
    if not logo_path or not os.path.exists(logo_path):
        return None
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except Exception:
        logger.warning("Failed to load logo %s", logo_path)
        return None

    size_pct = max(0.01, min(1.0, size_pct))
    target_w = min(frame_w, max(1, round(size_pct * frame_w)))
    logo = _resize_logo(logo, target_w)
    logo = _apply_opacity(logo, opacity)

    cw, ch = logo.size
    margin = round(MARGIN_PCT * frame_w)
    x, y = _anchor(position, frame_w, frame_h, cw, ch, margin)
    return {"logo": logo, "x": x, "y": y}


def render_frame(img: Image.Image, layout: dict) -> None:
    """Composite the prepared logo onto `img` in-place."""
    base = img.convert("RGBA")
    base.alpha_composite(layout["logo"], (layout["x"], layout["y"]))
    img.paste(base.convert("RGB"))
