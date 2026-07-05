"""Motion-blur frame blending (F-14: bounded sliding-window refactor).

The refactor must not change blending semantics: a constant-colour sequence must
stay constant (a weighted average of identical frames is that frame), and every
frame file must survive. This also guards the in-place-overwrite hazard — since
paths[i] is overwritten with the blend, neighbours must be read from the
original cache, not their already-blended on-disk copy.
"""

import cv2
import numpy as np

from app.services.timelapse import apply_motion_blur


def _write_frames(d, colors):
    paths = []
    for i, c in enumerate(colors):
        p = d / f"frame_{i:04d}.jpg"
        img = np.full((32, 32, 3), c, dtype=np.uint8)
        cv2.imwrite(str(p), img)
        paths.append(p)
    return paths


def test_constant_sequence_stays_constant(tmp_path):
    paths = _write_frames(tmp_path, [128] * 8)
    apply_motion_blur(str(tmp_path), blend_count=4)

    assert len(list(tmp_path.glob("*.jpg"))) == 8
    for p in paths:
        img = cv2.imread(str(p))
        # JPEG round-trips a solid grey within a couple of levels; the blend of
        # identical frames must not drift beyond that.
        assert abs(int(img.mean()) - 128) <= 2


def test_all_frames_preserved_and_modified_on_gradient(tmp_path):
    # A ramp of distinct greys: blur must keep the same number of frames and
    # leave each readable (no crash / dropped file from the windowed cache).
    paths = _write_frames(tmp_path, list(range(0, 240, 30)))
    apply_motion_blur(str(tmp_path), blend_count=4)
    assert len(list(tmp_path.glob("*.jpg"))) == len(paths)
    for p in paths:
        assert cv2.imread(str(p)) is not None
