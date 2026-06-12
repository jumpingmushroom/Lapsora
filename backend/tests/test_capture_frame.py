"""capture_frame orchestration (bytes-source path).

capture_frame is the product's core loop but only its pure helpers were tested.
These cover the bytes-source (go2rtc/HTTP) orchestration end to end: fetch ->
corruption gate -> resize -> file written -> DB row committed.
"""

import asyncio
import io
import os

import numpy as np
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, patch

from app.models import Base, Capture, Profile, Stream


def _make_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _seed(Session):
    db = Session()
    s = Stream(name="S", url="enc", source_type="go2rtc", go2rtc_name="cam")
    db.add(s)
    db.commit()
    db.refresh(s)
    p = Profile(stream_id=s.id, name="P", capture_mode="always", interval_seconds=60, enabled=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    pid = p.id
    db.close()
    return pid


def _clean_jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 120, 120)).save(buf, "JPEG")
    return buf.getvalue()


def _corrupt_jpeg():
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    arr[:, :, 1] = 130  # solid green block — trips _is_frame_corrupt
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, "JPEG")
    return buf.getvalue()


def test_capture_frame_bytes_source_writes_file_and_row(tmp_path, monkeypatch):
    Session = _make_session()
    pid = _seed(Session)
    from app.services import capture

    monkeypatch.setattr(capture, "SessionLocal", Session)
    monkeypatch.setattr(capture.settings, "DATA_DIR", str(tmp_path))
    with patch("app.services.providers.fetch_jpeg_bytes", new=AsyncMock(return_value=_clean_jpeg())):
        asyncio.run(capture.capture_frame(pid))

    db = Session()
    rows = db.query(Capture).all()
    assert len(rows) == 1
    assert rows[0].profile_id == pid
    assert os.path.exists(os.path.join(str(tmp_path), rows[0].file_path))
    db.close()


def test_capture_frame_discards_corrupt_bytes_frame(tmp_path, monkeypatch):
    Session = _make_session()
    pid = _seed(Session)
    from app.services import capture

    monkeypatch.setattr(capture, "SessionLocal", Session)
    monkeypatch.setattr(capture.settings, "DATA_DIR", str(tmp_path))
    with patch("app.services.providers.fetch_jpeg_bytes", new=AsyncMock(return_value=_corrupt_jpeg())):
        asyncio.run(capture.capture_frame(pid))

    db = Session()
    assert db.query(Capture).count() == 0  # corrupt frame -> no row
    db.close()


def test_capture_frame_outside_window_writes_nothing(tmp_path, monkeypatch):
    Session = _make_session()
    # Manual window that never includes "now": start==end at an impossible split.
    db = Session()
    s = Stream(name="S", url="enc", source_type="go2rtc", go2rtc_name="cam")
    db.add(s)
    db.commit()
    db.refresh(s)
    p = Profile(
        stream_id=s.id, name="P", capture_mode="manual",
        active_start_time="03:00", active_end_time="03:00", enabled=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    pid = p.id
    db.close()

    from app.services import capture

    monkeypatch.setattr(capture, "SessionLocal", Session)
    monkeypatch.setattr(capture.settings, "DATA_DIR", str(tmp_path))
    fetch = AsyncMock(return_value=_clean_jpeg())
    with patch("app.services.providers.fetch_jpeg_bytes", new=fetch), \
            patch.object(capture, "_is_within_active_window", return_value=False):
        asyncio.run(capture.capture_frame(pid))

    fetch.assert_not_awaited()
    db = Session()
    assert db.query(Capture).count() == 0
    db.close()
