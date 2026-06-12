"""Snapshot-source dispatch (services.providers).

This seam routes every capture/health/preview/test call to the right backend by
source_type; a dispatch bug silently breaks an entire source class, yet it had
no tests. The underlying backends are mocked — we assert routing only.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import encrypt
from app.services import providers


def _stream(**kw):
    base = dict(
        id=1, source_type="rtsp", url=encrypt("rtsp://cam/stream"),
        go2rtc_name=None, auth_type="none", auth_username=None,
        auth_secret=None, auth_header_name=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_fetch_jpeg_bytes_dispatches_go2rtc():
    s = _stream(source_type="go2rtc", go2rtc_name="cam1")
    with patch.object(providers.go2rtc, "get_go2rtc_url", return_value="http://g"), \
            patch.object(providers.go2rtc, "grab_frame", new=AsyncMock(return_value=b"JPG")) as gf:
        out = await providers.fetch_jpeg_bytes(s, db=None)
    assert out == b"JPG"
    gf.assert_awaited_once_with("http://g", "cam1")


@pytest.mark.asyncio
async def test_fetch_jpeg_bytes_go2rtc_unconfigured_raises():
    s = _stream(source_type="go2rtc", go2rtc_name="cam1")
    with patch.object(providers.go2rtc, "get_go2rtc_url", return_value=None):
        with pytest.raises(RuntimeError):
            await providers.fetch_jpeg_bytes(s, db=None)


@pytest.mark.asyncio
async def test_fetch_jpeg_bytes_http_snapshot_decrypts_url():
    s = _stream(source_type="http_snapshot", url=encrypt("http://cam/snap"))
    with patch.object(providers.http_source, "grab_snapshot", new=AsyncMock(return_value=b"S")) as g:
        out = await providers.fetch_jpeg_bytes(s, db=None)
    assert out == b"S"
    assert g.await_args.args[0] == "http://cam/snap"


@pytest.mark.asyncio
async def test_fetch_jpeg_bytes_http_mjpeg():
    s = _stream(source_type="http_mjpeg", url=encrypt("http://cam/mjpeg"))
    with patch.object(providers.http_source, "grab_mjpeg_frame", new=AsyncMock(return_value=b"M")):
        out = await providers.fetch_jpeg_bytes(s, db=None)
    assert out == b"M"


@pytest.mark.asyncio
async def test_fetch_jpeg_bytes_rtsp_not_handled_here():
    with pytest.raises(RuntimeError):
        await providers.fetch_jpeg_bytes(_stream(source_type="rtsp"), db=None)


@pytest.mark.asyncio
async def test_grab_preview_rtsp_uses_rtsp_grab_frame():
    s = _stream(source_type="rtsp", url=encrypt("rtsp://cam/x"))
    with patch.object(providers.rtsp, "grab_frame", new=AsyncMock(return_value=b"R")) as g:
        out = await providers.grab_preview(s, db=None)
    assert out == b"R"
    assert g.await_args.args[0] == "rtsp://cam/x"


@pytest.mark.asyncio
async def test_test_source_http_snapshot_reports_byte_count():
    s = _stream(source_type="http_snapshot", url=encrypt("http://cam/snap"))
    with patch.object(providers.http_source, "grab_snapshot", new=AsyncMock(return_value=b"abcd")):
        res = await providers.test_source(s, db=None)
    assert res["success"] is True
    assert res["details"]["bytes"] == 4


@pytest.mark.asyncio
async def test_test_source_swallows_errors_into_failure_result():
    s = _stream(source_type="rtsp", url=encrypt("rtsp://cam/x"))
    with patch.object(providers.rtsp, "test_connection", new=AsyncMock(side_effect=RuntimeError("boom"))):
        res = await providers.test_source(s, db=None)
    assert res["success"] is False
    assert "boom" in res["message"]
