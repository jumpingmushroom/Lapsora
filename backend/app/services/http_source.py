"""Generic HTTP image source — single-snapshot URLs and MJPEG streams.

Covers the large class of cameras and devices that expose a plain JPEG over
HTTP: generic IP-cam ``/snapshot.cgi`` endpoints, OctoPrint
(``?action=snapshot``), Frigate ``latest.jpg``, UniFi Protect, Reolink/Amcrest
CGI, and public/weather webcams. Anything exotic (RTMP/HLS/WebRTC/ONVIF) is left
to go2rtc, which Lapsora already supports.
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(15.0)
MJPEG_TIMEOUT = httpx.Timeout(15.0, read=10.0)
MAX_MJPEG_BYTES = 20 * 1024 * 1024  # cap so a never-terminating stream can't hang

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


def build_auth(
    auth_type: str | None,
    username: str | None,
    secret: str | None,
    header_name: str | None,
) -> tuple[httpx.Auth | None, dict[str, str]]:
    """Translate stored auth config into (httpx auth, extra headers).

    - none   → no auth
    - basic  → httpx.BasicAuth
    - digest → httpx.DigestAuth
    - bearer → ``Authorization: Bearer <secret>`` header
    - header → arbitrary ``<header_name>: <secret>`` header (e.g. X-API-Key)
    """
    auth_type = (auth_type or "none").lower()
    if auth_type == "basic":
        return httpx.BasicAuth(username or "", secret or ""), {}
    if auth_type == "digest":
        return httpx.DigestAuth(username or "", secret or ""), {}
    if auth_type == "bearer":
        return None, {"Authorization": f"Bearer {secret or ''}"}
    if auth_type == "header":
        if header_name and secret:
            return None, {header_name: secret}
        return None, {}
    return None, {}


async def grab_snapshot(
    url: str,
    auth: tuple[httpx.Auth | None, dict[str, str]] | None = None,
    retries: int = 3,
) -> bytes:
    """Fetch a single JPEG from an HTTP snapshot URL, retrying on 5xx."""
    httpx_auth, headers = auth or (None, {})
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        for attempt in range(1, retries + 1):
            resp = await client.get(url, auth=httpx_auth, headers=headers)
            if resp.status_code >= 500 and attempt < retries:
                from app.url_utils import mask_url
                logger.warning(
                    "HTTP snapshot %s returned %s (attempt %d/%d), retrying...",
                    mask_url(url), resp.status_code, attempt, retries,
                )
                await asyncio.sleep(1)
                continue
            resp.raise_for_status()
            content = resp.content
            if not content:
                raise RuntimeError("Empty response from snapshot URL")
            ctype = resp.headers.get("content-type", "")
            if ctype and not (ctype.startswith("image/") or "octet-stream" in ctype):
                # Some cams mislabel; only hard-fail on obvious non-images (HTML).
                if "text/html" in ctype or "application/json" in ctype:
                    raise RuntimeError(
                        f"Snapshot URL returned {ctype!r}, not an image "
                        "(check the URL and auth)"
                    )
            if not content.startswith(JPEG_SOI):
                raise RuntimeError("Snapshot response is not a JPEG image")
            return content
    raise RuntimeError("grab_snapshot exhausted retries")


async def grab_mjpeg_frame(
    url: str,
    auth: tuple[httpx.Auth | None, dict[str, str]] | None = None,
) -> bytes:
    """Pull a single complete JPEG frame from a multipart MJPEG stream.

    Scans the multipart body for the first ``FFD8 … FFD9`` JPEG and returns it,
    then closes the connection. Bounded by a read timeout and a byte cap so a
    stalled or never-terminating stream can't hang a scheduled capture.
    """
    httpx_auth, headers = auth or (None, {})
    buffer = bytearray()
    async with httpx.AsyncClient(timeout=MJPEG_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", url, auth=httpx_auth, headers=headers) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                buffer.extend(chunk)
                start = buffer.find(JPEG_SOI)
                if start != -1:
                    end = buffer.find(JPEG_EOI, start + 2)
                    if end != -1:
                        return bytes(buffer[start : end + 2])
                    # Drop bytes before SOI to keep the buffer bounded.
                    if start > 0:
                        del buffer[:start]
                if len(buffer) > MAX_MJPEG_BYTES:
                    raise RuntimeError("No complete JPEG frame found in MJPEG stream")
    raise RuntimeError("MJPEG stream ended before a complete frame was received")
