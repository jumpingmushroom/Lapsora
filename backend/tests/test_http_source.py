import httpx
import pytest

from app.services import http_source


# --- build_auth (pure) ---


def test_build_auth_none():
    auth, headers = http_source.build_auth("none", None, None, None)
    assert auth is None and headers == {}


def test_build_auth_basic_and_digest():
    auth, headers = http_source.build_auth("basic", "user", "pass", None)
    assert isinstance(auth, httpx.BasicAuth) and headers == {}
    auth, headers = http_source.build_auth("digest", "user", "pass", None)
    assert isinstance(auth, httpx.DigestAuth) and headers == {}


def test_build_auth_bearer():
    auth, headers = http_source.build_auth("bearer", None, "tok123", None)
    assert auth is None
    assert headers == {"Authorization": "Bearer tok123"}


def test_build_auth_custom_header():
    auth, headers = http_source.build_auth("header", None, "secretval", "X-API-Key")
    assert auth is None
    assert headers == {"X-API-Key": "secretval"}


def test_build_auth_header_missing_name_is_noop():
    auth, headers = http_source.build_auth("header", None, "secretval", None)
    assert auth is None and headers == {}


# --- fakes for httpx ---

JPEG = b"\xff\xd8\xff\xe0jpegbody\xff\xd9"


class _FakeResp:
    def __init__(self, chunks, status=200, content_type="image/jpeg"):
        self._chunks = chunks
        self.status_code = status
        self.headers = {"content-type": content_type} if content_type else {}

    @property
    def content(self):
        return b"".join(self._chunks)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c


class _FakeStreamCtx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        return False


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, **kw):
        return _FakeStreamCtx(self._resp)

    async def get(self, url, **kw):
        return self._resp


def _patch_client(monkeypatch, resp):
    monkeypatch.setattr(
        http_source.httpx, "AsyncClient", lambda *a, **k: _FakeClient(resp)
    )


# --- grab_snapshot ---


@pytest.mark.asyncio
async def test_grab_snapshot_returns_jpeg(monkeypatch):
    _patch_client(monkeypatch, _FakeResp([JPEG]))
    out = await http_source.grab_snapshot("http://cam/snap.jpg")
    assert out == JPEG


@pytest.mark.asyncio
async def test_grab_snapshot_rejects_html(monkeypatch):
    _patch_client(monkeypatch, _FakeResp([b"<html>nope</html>"], content_type="text/html"))
    with pytest.raises(RuntimeError):
        await http_source.grab_snapshot("http://cam/login")


@pytest.mark.asyncio
async def test_grab_snapshot_rejects_non_jpeg_bytes(monkeypatch):
    _patch_client(monkeypatch, _FakeResp([b"\x89PNGdata"], content_type="image/png"))
    with pytest.raises(RuntimeError):
        await http_source.grab_snapshot("http://cam/snap.png")


# --- grab_mjpeg_frame ---


@pytest.mark.asyncio
async def test_grab_mjpeg_extracts_first_frame(monkeypatch):
    # Multipart preamble, then the JPEG split across two chunks, then trailer.
    chunks = [
        b"--boundary\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8\xff\xe0jpeg",
        b"body\xff\xd9\r\n--boundary\r\n",
    ]
    _patch_client(monkeypatch, _FakeResp(chunks))
    out = await http_source.grab_mjpeg_frame("http://cam/mjpeg")
    assert out == JPEG


@pytest.mark.asyncio
async def test_grab_mjpeg_errors_when_no_frame(monkeypatch):
    _patch_client(monkeypatch, _FakeResp([b"no jpeg here at all"]))
    with pytest.raises(RuntimeError):
        await http_source.grab_mjpeg_frame("http://cam/mjpeg")
