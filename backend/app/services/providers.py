"""Snapshot-source provider seam.

Single place that maps a stream's ``source_type`` to the code that talks to it.
Adding a new source type means extending the dispatch here (plus its own service
module) — capture, health checks, the test endpoint and the preview endpoint all
route through these functions instead of duplicating ``if source_type`` ladders.

Source types:
- ``rtsp``          — FFmpeg/FFprobe (see services.rtsp; HDR handled in capture.py)
- ``go2rtc``        — go2rtc HTTP frame API (see services.go2rtc)
- ``http_snapshot`` — single JPEG over HTTP (see services.http_source)
- ``http_mjpeg``    — first frame of a multipart MJPEG stream (services.http_source)
"""

import logging

from app.config import decrypt
from app.services import go2rtc, http_source, rtsp

logger = logging.getLogger(__name__)

HTTP_SOURCE_TYPES = ("http_snapshot", "http_mjpeg")
# Sources that yield JPEG bytes directly (vs. RTSP's FFmpeg-to-file path).
BYTES_SOURCE_TYPES = ("go2rtc", *HTTP_SOURCE_TYPES)


def _stream_auth(stream):
    """Build httpx auth/headers from a stream's stored (encrypted) auth config."""
    secret = None
    if stream.auth_secret:
        try:
            secret = decrypt(stream.auth_secret)
        except Exception:
            logger.warning("Could not decrypt auth secret for stream %s", stream.id)
    return http_source.build_auth(
        stream.auth_type, stream.auth_username, secret, stream.auth_header_name
    )


async def fetch_jpeg_bytes(stream, db) -> bytes:
    """Return a JPEG frame for a bytes-based source (go2rtc / http_*).

    RTSP is *not* handled here — it captures straight to file with corruption
    retries in capture.py. Raises on failure.
    """
    if stream.source_type == "go2rtc":
        base_url = go2rtc.get_go2rtc_url(db)
        if not base_url:
            raise RuntimeError("go2rtc URL not configured")
        return await go2rtc.grab_frame(base_url, stream.go2rtc_name)

    if stream.source_type in HTTP_SOURCE_TYPES:
        url = decrypt(stream.url)
        auth = _stream_auth(stream)
        if stream.source_type == "http_snapshot":
            return await http_source.grab_snapshot(url, auth)
        return await http_source.grab_mjpeg_frame(url, auth)

    raise RuntimeError(f"fetch_jpeg_bytes does not handle source type {stream.source_type!r}")


async def grab_preview(stream, db) -> bytes:
    """Return a JPEG preview frame for any source type."""
    if stream.source_type in BYTES_SOURCE_TYPES:
        return await fetch_jpeg_bytes(stream, db)
    # rtsp
    return await rtsp.grab_frame(decrypt(stream.url))


async def test_source(stream, db) -> dict:
    """Test connectivity to a stream's source. Returns {success, message, details}."""
    try:
        if stream.source_type == "go2rtc":
            base_url = go2rtc.get_go2rtc_url(db)
            if not base_url:
                return {"success": False, "message": "go2rtc URL not configured", "details": None}
            return await go2rtc.test_stream(base_url, stream.go2rtc_name)

        if stream.source_type in HTTP_SOURCE_TYPES:
            jpeg = await fetch_jpeg_bytes(stream, db)
            return {
                "success": True,
                "message": "Snapshot successful",
                "details": {"bytes": len(jpeg)},
            }

        # rtsp
        return await rtsp.test_connection(decrypt(stream.url))
    except Exception as exc:
        return {"success": False, "message": str(exc), "details": None}
