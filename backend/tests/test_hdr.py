"""HDR exposure fusion (services.hdr._fuse_hdr_frames).

Called from the capture path for HDR profiles; the OpenCV Mertens merge + white
balance had no tests. We feed synthetic bracketed frames and assert a valid
output is produced with the source dimensions.
"""

import os

import cv2
import numpy as np
import pytest

from app.services import hdr


def _write(path, value):
    cv2.imwrite(path, np.full((48, 64, 3), value, dtype=np.uint8))


def test_fuse_hdr_frames_produces_output(tmp_path):
    paths = []
    for i, val in enumerate((60, 120, 200)):
        p = str(tmp_path / f"f{i}.jpg")
        _write(p, val)
        paths.append(p)
    out = str(tmp_path / "out.jpg")

    result = hdr._fuse_hdr_frames(paths, out, quality=90)

    assert os.path.exists(out)
    assert result["width"] == 64
    assert result["height"] == 48
    assert result["file_size"] > 0
    # Output must be a readable image of the right size.
    img = cv2.imread(out)
    assert img is not None
    assert img.shape[:2] == (48, 64)


def test_fuse_hdr_frames_raises_on_unreadable_frame(tmp_path):
    out = str(tmp_path / "out.jpg")
    with pytest.raises(RuntimeError):
        hdr._fuse_hdr_frames([str(tmp_path / "does_not_exist.jpg")], out, quality=90)
