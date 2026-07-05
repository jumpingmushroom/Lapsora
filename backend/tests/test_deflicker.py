"""Deflicker brightness handling (F-26).

An unreadable frame must not drag the smoothed brightness target toward black
and darken its readable neighbours — its brightness is interpolated from the
readable frames around it before smoothing.
"""

import cv2
import numpy as np

from app.services.deflicker import deflicker_frames


def test_unreadable_frame_does_not_darken_neighbors(tmp_path):
    n = 9
    gap = n // 2
    srcs, dsts = [], []
    for i in range(n):
        s = tmp_path / f"in_{i:02d}.jpg"
        d = tmp_path / f"out_{i:02d}.jpg"
        if i == gap:
            s.write_bytes(b"not a jpeg")  # cv2.imread -> None (unreadable)
        else:
            cv2.imwrite(str(s), np.full((32, 32, 3), 128, np.uint8))
        srcs.append(str(s))
        dsts.append(str(d))

    # "heavy" (large sigma) makes a single 0.0 brightness sample bleed far into
    # its neighbours without the interpolation fix.
    deflicker_frames(srcs, dsts, strength="heavy")

    for i in (gap - 1, gap + 1):
        img = cv2.imread(dsts[i])
        assert img is not None, f"neighbour {i} was not written"
        assert abs(int(img.mean()) - 128) <= 3, f"neighbour {i} darkened to {img.mean()}"
