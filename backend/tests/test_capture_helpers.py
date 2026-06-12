"""Capture-service pure helpers: corruption detection, resize, active window.

These are core to every capture but were previously untested.
"""

from datetime import datetime
from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.services import capture


def test_resize_and_save_resizes(tmp_path):
    p = tmp_path / "f.jpg"
    Image.new("RGB", (100, 80), (120, 120, 120)).save(p, "JPEG")
    w, h, size = capture._resize_and_save(str(p), 50, 40, 85)
    assert (w, h) == (50, 40)
    assert size > 0
    with Image.open(p) as out:
        assert out.size == (50, 40)


def test_resize_and_save_without_dimensions_keeps_size(tmp_path):
    p = tmp_path / "f.jpg"
    Image.new("RGB", (64, 48), (10, 20, 30)).save(p, "JPEG")
    w, h, _ = capture._resize_and_save(str(p), None, None, 90)
    assert (w, h) == (64, 48)


def test_is_frame_corrupt_clean_image(tmp_path):
    p = tmp_path / "clean.jpg"
    Image.new("RGB", (200, 200), (128, 128, 128)).save(p, "JPEG")
    assert capture._is_frame_corrupt(str(p)) is False


def test_is_frame_corrupt_green_block(tmp_path):
    p = tmp_path / "green.jpg"
    arr = np.zeros((200, 200, 3), dtype=np.uint8)
    arr[:, :, 1] = 130  # solid green in the detector's R<15,100<=G<=160,B<15 range
    Image.fromarray(arr, "RGB").save(p, "JPEG")
    assert capture._is_frame_corrupt(str(p)) is True


def test_active_window_always():
    profile = SimpleNamespace(capture_mode="always")
    assert capture._is_within_active_window(profile, None, datetime(2026, 6, 12, 3, 0)) is True


def test_active_window_manual_inside():
    profile = SimpleNamespace(
        capture_mode="manual", active_start_time="08:00", active_end_time="18:00"
    )
    assert capture._is_within_active_window(profile, None, datetime(2026, 6, 12, 12, 0)) is True


def test_active_window_manual_outside():
    profile = SimpleNamespace(
        capture_mode="manual", active_start_time="08:00", active_end_time="18:00"
    )
    assert capture._is_within_active_window(profile, None, datetime(2026, 6, 12, 20, 0)) is False


def test_active_window_manual_overnight_span():
    profile = SimpleNamespace(
        capture_mode="manual", active_start_time="22:00", active_end_time="06:00"
    )
    # 02:00 is inside the overnight window, 12:00 is outside.
    assert capture._is_within_active_window(profile, None, datetime(2026, 6, 12, 2, 0)) is True
    assert capture._is_within_active_window(profile, None, datetime(2026, 6, 12, 12, 0)) is False
