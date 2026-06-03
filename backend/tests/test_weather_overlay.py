from datetime import datetime
from types import SimpleNamespace

from PIL import Image

from app.services import weather_overlay as wo


def _cap(temp, code, is_day=True):
    return SimpleNamespace(
        weather_temp=temp, weather_code=code, weather_is_day=is_day,
        captured_at=datetime(2026, 6, 3, 14, 32),
    )


def test_locked_layout_is_constant_across_conditions():
    caps = [_cap(18.0, 0), _cap(15.0, 95), _cap(-2.0, 73)]  # Clear / Thunderstorm / Snow
    layout = wo.compute_layout(caps, "glass", "C", 24)
    assert layout["card_w"] > 0
    assert layout["card_h"] > 0


def _solid_frame():
    return Image.new("RGB", (640, 360), (40, 90, 140))


def test_render_each_style_modifies_frame_without_error():
    caps = [_cap(18.0, 0), _cap(15.0, 95), _cap(-2.0, 73)]
    for style in ("minimal", "badge", "glass", "strip"):
        layout = wo.compute_layout(caps, style, "C", 24) if style != "minimal" else None
        img = _solid_frame()
        before = list(img.getdata())
        wo.render_frame(img, caps[0], style, "bottom-right", "C", 24, layout)
        after = list(img.getdata())
        assert img.size == (640, 360)
        assert before != after, f"style {style} did not modify the frame"


def test_render_modern_box_position_is_stable_across_conditions():
    caps = [_cap(18.0, 0), _cap(15.0, 95)]
    layout = wo.compute_layout(caps, "glass", "C", 24)
    cw, ch = layout["card_w"], layout["card_h"]
    x = 640 - cw - wo.MARGIN
    y = 360 - ch - wo.MARGIN
    for cap in caps:
        img = _solid_frame()
        base_pixel = img.getpixel((x - 5, y - 5))  # just outside the card stays untouched
        wo.render_frame(img, cap, "glass", "bottom-right", "C", 24, layout)
        assert img.getpixel((x - 5, y - 5)) == base_pixel
        assert img.getpixel((x + cw // 2, y + ch // 2)) != base_pixel  # inside changed
