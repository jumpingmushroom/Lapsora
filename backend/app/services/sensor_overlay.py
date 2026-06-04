"""Home Assistant sensor overlays baked onto timelapse frames.

A single panel geometry is computed once per render (compute_layout) so the
overlay never resizes/jumps between frames as values change. Layout is derived
from the sensor data actually recorded in the captures, not live profile config.
"""

import functools
import json
import logging

from PIL import Image, ImageDraw, ImageFont

from app.services.overlay_glass import draw_glass_card
from app.services.sensor_icons import icon_path_for

logger = logging.getLogger(__name__)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PAD_H = 14      # horizontal padding inside the card
PAD_V = 10      # vertical padding inside the card
ICON_GAP = 7    # gap between icon and label
GAP = 12        # min gap between label column and value column
ROW_GAP = 6     # vertical gap between rows
MARGIN = 16     # distance from the frame edge


def _font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _text_w(draw, text, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_h(font) -> int:
    try:
        a, d = font.getmetrics()
        return a + d
    except Exception:
        return 12


@functools.lru_cache(maxsize=64)
def _icon(key, size):
    path = icon_path_for(key)
    if not path:
        return None
    try:
        return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        logger.warning("Failed to load sensor icon %s", path)
        return None


def _parse(cap) -> dict:
    raw = getattr(cap, "sensor_data", None)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _value_text(entry: dict) -> str:
    if not entry or entry.get("value") is None:
        return "—"
    return f"{entry.get('value')}{entry.get('unit') or ''}"


def compute_layout(captures, font_size: int = 24) -> dict | None:
    """Compute one fixed panel geometry from the union of sensors recorded in
    `captures`. Returns a dict for render_frame, or None when no sensor data."""
    label_font = _font(max(11, int(font_size * 0.6)))
    value_font = _font(int(font_size * 0.7))
    icon_size = int(font_size * 0.8)

    order: list[str] = []
    meta: dict[str, dict] = {}
    for cap in captures:
        for eid, entry in _parse(cap).items():
            if eid not in meta:
                order.append(eid)
                meta[eid] = {"label": entry.get("label") or eid, "icon": entry.get("icon") or ""}
    if not order:
        return None

    measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    max_label_w = max(_text_w(measure, meta[eid]["label"], label_font) for eid in order)
    max_value_w = 0
    for cap in captures:
        data = _parse(cap)
        for eid in order:
            max_value_w = max(max_value_w, _text_w(measure, _value_text(data.get(eid)), value_font))

    row_h = max(icon_size, _text_h(label_font), _text_h(value_font))
    n = len(order)
    card_w = PAD_H + icon_size + ICON_GAP + max_label_w + GAP + max_value_w + PAD_H
    card_h = PAD_V + n * row_h + (n - 1) * ROW_GAP + PAD_V
    return {
        "order": order,
        "meta": meta,
        "label_font": label_font,
        "value_font": value_font,
        "icon_size": icon_size,
        "row_h": row_h,
        "card_w": card_w,
        "card_h": card_h,
    }


def _anchor(position, W, H, cw, ch):
    m = MARGIN
    if position == "top-right":
        return W - cw - m, m
    if position == "bottom-left":
        return m, H - ch - m
    if position == "bottom-right":
        return W - cw - m, H - ch - m
    return m, m  # top-left default


def render_frame(img, cap, position, layout) -> None:
    """Draw the sensor overlay onto `img` in-place using the locked `layout`."""
    if layout is None:
        return
    data = _parse(cap)
    order = layout["order"]
    cw, ch = layout["card_w"], layout["card_h"]
    icon_size = layout["icon_size"]
    row_h = layout["row_h"]
    label_font = layout["label_font"]
    value_font = layout["value_font"]
    W, H = img.size
    x, y = _anchor(position, W, H, cw, ch)

    base = img.convert("RGBA")
    base = draw_glass_card(base, x, y, cw, ch)
    draw = ImageDraw.Draw(base)

    ix = x + PAD_H
    label_x = ix + icon_size + ICON_GAP
    value_right = x + cw - PAD_H
    cy = y + PAD_V
    for eid in order:
        entry = data.get(eid, {})
        m = layout["meta"][eid]
        ic = _icon(m["icon"], icon_size)
        if ic is not None:
            base.paste(ic, (ix, cy + (row_h - icon_size) // 2), ic)
        lab_y = cy + (row_h - _text_h(label_font)) // 2
        draw.text((label_x, lab_y), m["label"], font=label_font, fill=(255, 255, 255, 220))
        vtext = _value_text(entry)
        vw = _text_w(draw, vtext, value_font)
        val_y = cy + (row_h - _text_h(value_font)) // 2
        draw.text((value_right - vw, val_y), vtext, font=value_font, fill=(255, 255, 255, 255))
        cy += row_h + ROW_GAP

    img.paste(base.convert("RGB"))
