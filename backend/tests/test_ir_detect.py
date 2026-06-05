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
