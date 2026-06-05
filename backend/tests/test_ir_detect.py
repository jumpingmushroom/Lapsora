import numpy as np
from PIL import Image

from app.services.ir_detect import mean_chroma


def _img(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr.astype("uint8"), "RGB")


def test_solid_grey_is_near_zero():
    arr = np.full((120, 160, 3), 128, dtype="uint8")  # R==G==B everywhere
    assert mean_chroma(_img(arr)) < 1.0


def test_grey_gradient_is_near_zero():
    # Luminance gradient but still R==G==B per pixel -> chroma ~0
    col = np.linspace(0, 255, 160).astype("uint8")
    arr = np.repeat(col[None, :, None], 120, axis=0)
    arr = np.repeat(arr, 3, axis=2)
    assert mean_chroma(_img(arr)) < 1.0


def test_saturated_red_is_high():
    arr = np.zeros((120, 160, 3), dtype="uint8")
    arr[:, :, 0] = 255  # pure red -> spread 255 -> 100.0
    assert mean_chroma(_img(arr)) > 90.0


def test_mid_saturation_is_in_between():
    arr = np.zeros((120, 160, 3), dtype="uint8")
    arr[:, :, 0] = 130
    arr[:, :, 1] = 100
    arr[:, :, 2] = 100  # spread 30 -> ~11.8
    val = mean_chroma(_img(arr))
    assert 5.0 < val < 25.0


def test_grayscale_mode_image_is_near_zero():
    # An L-mode (single channel) image must still be handled (converted to RGB)
    img = Image.fromarray(np.full((120, 160), 100, dtype="uint8"), "L")
    assert mean_chroma(img) < 1.0


import os
from unittest.mock import patch

import pytest

from app.services import capture


class _StubStream:
    id = 1
    name = "cam"
    source_type = "go2rtc"
    go2rtc_name = "cam"
    url = None


class _StubProfile:
    id = 1
    name = "p"
    resolution_width = None
    resolution_height = None
    quality = 85
    hdr_enabled = False
    weather_enabled = False
    ha_sensors = None
    ir_only = True
    ir_chroma_threshold = 10.0

    def __init__(self):
        self.stream = _StubStream()


def _jpeg_bytes(arr):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr.astype("uint8"), "RGB").save(buf, "JPEG", quality=95)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_capture_discards_colour_frame_when_ir_only(tmp_path, monkeypatch):
    import numpy as np

    profile = _StubProfile()
    colour = np.zeros((120, 160, 3), dtype="uint8")
    colour[:, :, 0] = 255  # pure red -> chroma 100 > threshold 10

    class _Q:
        def filter(self, *a, **k): return self
        def first(self): return profile
    class _DB:
        def query(self, *a, **k): return _Q()
        def add(self, *a, **k): pass
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    monkeypatch.setattr(capture, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(capture.settings, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(capture, "_is_within_active_window", lambda *a, **k: True)
    monkeypatch.setattr(capture, "_is_frame_corrupt", lambda *a, **k: False)

    async def _fake_fetch(stream, db):
        return _jpeg_bytes(colour)
    from app.services import providers
    monkeypatch.setattr(providers, "fetch_jpeg_bytes", _fake_fetch)

    captured = {}
    real_capture_init = capture.Capture
    monkeypatch.setattr(
        capture, "Capture",
        lambda **kw: captured.setdefault("record", kw) or real_capture_init(**kw),
    )

    await capture.capture_frame(1)

    assert "record" not in captured
    leftover = list(tmp_path.rglob("*.jpg"))
    assert leftover == []
