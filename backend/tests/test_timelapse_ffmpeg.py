"""ffmpeg command construction in generate_timelapse.

The encoder pipeline (codec/quality/resolution selection, concat input, vf
chain) had no tests — a bad command only failed at generation time in prod. We
run the real generate_timelapse with a mocked subprocess so the actual
command-building code executes, and assert the resulting argv.
"""

import asyncio
import os

import cv2
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from app.models import Base, Capture, Profile, Stream


class _FakeProc:
    def __init__(self, stdout=b"", returncode=0):
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self):
        return (self._stdout, b"")


def _make_fake_exec(captured):
    async def _fake(*args, **kwargs):
        captured.append(args)
        # The encode call ("-f concat ...") and the thumbnail call ("-ss ...")
        # both write their output to the last argument — create it so the
        # subsequent getsize/imread succeed.
        if "concat" in args or ("-ss" in args and "-frames:v" in args):
            with open(args[-1], "wb") as f:
                f.write(b"x")
        stdout = b'{"format": {"duration": "1.0"}}' if "-show_format" in args else b""
        return _FakeProc(stdout=stdout)

    return _fake


def _seed_with_frames(Session, data_dir, n=3):
    db = Session()
    s = Stream(name="S", url="enc")
    db.add(s)
    db.commit()
    db.refresh(s)
    p = Profile(stream_id=s.id, name="P")
    db.add(p)
    db.commit()
    db.refresh(p)
    pid = p.id

    cap_dir = os.path.join(data_dir, "captures")
    os.makedirs(cap_dir, exist_ok=True)
    from datetime import datetime
    for i in range(n):
        rel = f"captures/c{i}.jpg"
        cv2.imwrite(os.path.join(data_dir, rel), np.full((48, 64, 3), 100 + i * 10, dtype=np.uint8))
        db.add(Capture(profile_id=pid, file_path=rel, captured_at=datetime(2026, 1, 1, 12, i)))
    db.commit()
    db.close()
    return pid


def _run_generation(tmp_path, monkeypatch, **kwargs):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    pid = _seed_with_frames(Session, str(tmp_path))

    from app.services import timelapse
    from datetime import datetime

    monkeypatch.setattr(timelapse, "SessionLocal", Session)
    monkeypatch.setattr(timelapse.settings, "DATA_DIR", str(tmp_path))
    # Force the deterministic software path.
    monkeypatch.setattr(timelapse, "is_nvenc_available", lambda: False)
    monkeypatch.setattr(timelapse, "get_nvenc_encoders", lambda: {})

    captured: list = []
    with patch("asyncio.create_subprocess_exec", new=_make_fake_exec(captured)):
        asyncio.run(
            timelapse.generate_timelapse(
                profile_id=pid,
                period_type="custom",
                period_start=datetime(2026, 1, 1, 0, 0),
                period_end=datetime(2026, 1, 2, 0, 0),
                deflicker="off",
                **kwargs,
            )
        )
    encode_cmd = next(c for c in captured if "concat" in c)
    return encode_cmd, Session


def test_encode_uses_libx264_software_for_mp4(tmp_path, monkeypatch):
    cmd, _Session = _run_generation(tmp_path, monkeypatch, format="mp4", codec="auto", quality_preset="medium")
    assert "ffmpeg" in cmd[0]
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "libx264"
    assert "-crf" in cmd  # software quality is CRF-based
    assert "-f" in cmd and "concat" in cmd
    assert cmd[-1].endswith(".mp4")


def test_encode_webm_uses_vp9(tmp_path, monkeypatch):
    cmd, _Session = _run_generation(tmp_path, monkeypatch, format="webm", quality_preset="medium")
    assert cmd[cmd.index("-c:v") + 1] == "libvpx-vp9"
    assert cmd[-1].endswith(".webm")


def test_encode_h265_software(tmp_path, monkeypatch):
    cmd, _Session = _run_generation(tmp_path, monkeypatch, format="mp4", codec="h265", quality_preset="high")
    assert cmd[cmd.index("-c:v") + 1] == "libx265"


def test_resolution_scale_filter_applied(tmp_path, monkeypatch):
    cmd, _Session = _run_generation(
        tmp_path, monkeypatch, format="mp4", output_width=32, output_height=24
    )
    assert "-vf" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "scale=32:24" in vf


def test_generation_creates_timelapse_row(tmp_path, monkeypatch):
    _cmd, Session = _run_generation(tmp_path, monkeypatch, format="mp4")
    from app.models import Timelapse
    db = Session()
    rows = db.query(Timelapse).all()
    assert len(rows) == 1
    assert rows[0].format == "mp4"
    db.close()
