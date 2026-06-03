"""Styled weather overlays baked onto timelapse frames.

Styles: 'minimal' (legacy text box), 'badge', 'glass', 'strip'.
A single card width is computed once per render (compute_layout) so the
overlay never resizes/jumps between frames as the condition changes.
"""

import logging

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.services.weather import WMO_CODES, format_weather_text
from app.services.weather_icons import icon_path_for

logger = logging.getLogger(__name__)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PAD_H = 14      # horizontal padding inside the card
PAD_V = 10      # vertical padding inside the card
GAP = 10        # gap between icon and text
MARGIN = 16     # distance from the frame edge
RADIUS = 16     # card corner radius
_MODERN = ("badge", "glass", "strip")


def _font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _temp_text(temp: float, unit: str) -> str:
    if unit.upper() == "F":
        return f"{temp * 9 / 5 + 32:.0f}°F"
    return f"{temp:.0f}°C"


def _text_w(draw, text, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_h(font) -> int:
    try:
        a, d = font.getmetrics()
        return a + d
    except Exception:
        return 12


def _truncate(draw, text, font, max_w) -> str:
    if _text_w(draw, text, font) <= max_w:
        return text
    while text and _text_w(draw, text + "…", font) > max_w:
        text = text[:-1]
    return text + "…"


def _icon(code, is_day, size):
    path = icon_path_for(code, is_day)
    if not path:
        return None
    try:
        return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:
        logger.warning("Failed to load weather icon %s", path)
        return None


def compute_layout(captures, style: str, unit: str, font_size: int) -> dict:
    """Compute one fixed card geometry for the whole render.

    `captures` is the list of frame captures that have weather data.
    Returns a dict consumed by render_frame.
    """
    icon_size = int(font_size * 1.6)
    temp_font = _font(int(font_size * 1.2))
    cond_font = _font(max(10, int(font_size * 0.6)))

    measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    max_temp_w = 0
    max_cond_w = 0
    for cap in captures:
        if cap.weather_temp is None:
            continue
        max_temp_w = max(max_temp_w, _text_w(measure, _temp_text(cap.weather_temp, unit), temp_font))
        label = WMO_CODES.get(cap.weather_code or 0, "Unknown")
        max_cond_w = max(max_cond_w, _text_w(measure, label, cond_font))

    if style == "badge":
        text_w = max_temp_w
        content_h = max(icon_size, _text_h(temp_font))
    else:  # glass / strip
        text_w = max(max_temp_w, max_cond_w)
        content_h = max(icon_size, _text_h(temp_font) + 2 + _text_h(cond_font))

    card_w = PAD_H + icon_size + GAP + text_w + PAD_H
    card_h = content_h + 2 * PAD_V
    return {
        "icon_size": icon_size,
        "temp_font": temp_font,
        "cond_font": cond_font,
        "text_w": text_w,
        "card_w": card_w,
        "card_h": card_h,
    }


def _anchor(position, W, H, cw, ch):
    m = MARGIN
    if position == "top-left":
        return m, m
    if position == "top-right":
        return W - cw - m, m
    if position == "bottom-left":
        return m, H - ch - m
    return W - cw - m, H - ch - m  # bottom-right default


def _render_minimal(img, cap, position, unit, font_size):
    """Legacy plain black text box (unchanged behavior)."""
    draw = ImageDraw.Draw(img)
    text = format_weather_text(cap.weather_temp, cap.weather_code or 0, unit)
    font = _font(font_size)
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
    x, y = positions.get(position, positions["bottom-right"])
    draw.rectangle([x - 5, y - 5, x + tw + 5, y + th + 5], fill=(0, 0, 0, 128))
    draw.text((x, y), text, font=font, fill="white")


def _render_modern(img, cap, layout, style, position, unit):
    icon_size = layout["icon_size"]
    cw, ch = layout["card_w"], layout["card_h"]
    temp_font, cond_font = layout["temp_font"], layout["cond_font"]
    W, H = img.size
    x, y = _anchor(position, W, H, cw, ch)

    base = img.convert("RGBA")

    # frosted glass: blur the region behind the card, tint it, paste with rounded mask
    region = base.crop((x, y, x + cw, y + ch)).filter(ImageFilter.GaussianBlur(8))
    tint = Image.new("RGBA", (cw, ch), (20, 22, 28, 150))
    card = Image.alpha_composite(region, tint)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=RADIUS, fill=255)
    base.paste(card, (x, y), mask)

    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle([x, y, x + cw - 1, y + ch - 1], radius=RADIUS,
                           outline=(255, 255, 255, 70), width=1)

    # icon, vertically centered
    ic = _icon(cap.weather_code or 0, cap.weather_is_day, icon_size)
    ix = x + PAD_H
    iy = y + (ch - icon_size) // 2
    if ic is not None:
        base.paste(ic, (ix, iy), ic)

    tx = ix + icon_size + GAP
    temp_txt = _temp_text(cap.weather_temp, unit)

    if style == "badge":
        ty = y + (ch - _text_h(temp_font)) // 2
        draw.text((tx, ty), temp_txt, font=temp_font, fill=(255, 255, 255, 255))
    else:
        cond_txt = _truncate(draw, WMO_CODES.get(cap.weather_code or 0, "Unknown"),
                             cond_font, layout["text_w"])
        th, ch_t = _text_h(temp_font), _text_h(cond_font)
        block_h = th + 2 + ch_t
        ty = y + (ch - block_h) // 2
        draw.text((tx, ty), temp_txt, font=temp_font, fill=(255, 255, 255, 255))
        draw.text((tx, ty + th + 2), cond_txt, font=cond_font, fill=(255, 255, 255, 220))
        if style == "strip":
            sub = cap.captured_at.strftime("%H:%M")
            sw = _text_w(draw, sub, cond_font)
            draw.text((x + cw - PAD_H - sw, y + ch - ch_t - PAD_V),
                      sub, font=cond_font, fill=(255, 255, 255, 160))

    img.paste(base.convert("RGB"))


def render_frame(img, cap, style, position, unit, font_size, layout):
    """Draw the weather overlay onto `img` in-place.

    `layout` is the dict from compute_layout (required for modern styles,
    ignored for 'minimal').
    """
    if style in _MODERN and layout is not None:
        _render_modern(img, cap, layout, style, position, unit)
    else:
        _render_minimal(img, cap, position, unit, font_size)
