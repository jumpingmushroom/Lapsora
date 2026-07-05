"""Helpers for redacting credentials from source URLs before they reach logs,
error strings, or persisted/dispatched notifications.

Stream URLs (RTSP, HTTP snapshot/MJPEG) can embed ``user:password@host``.
ffmpeg echoes the full URL in its stderr, and httpx embeds it in exception
messages — both of which flow into capture-failure notifications (persisted and
dispatched via Apprise, which may leave the LAN). Redact before emitting.
"""

from urllib.parse import urlsplit, urlunsplit


def mask_url(url: str) -> str:
    """Return ``url`` with any embedded password replaced by ``•••``. Leaves URLs
    without credentials untouched; never raises."""
    try:
        parts = urlsplit(url)
        if not parts.password:
            return url
        netloc = f"{parts.username or ''}:•••@{parts.hostname or ''}"
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return url


def scrub_urls(text: str, *urls: str) -> str:
    """Replace every occurrence of the given credentialed ``urls`` in ``text``
    (e.g. ffmpeg stderr) with their masked form. Only masks URLs that actually
    carry a password, so it's a no-op for credential-free inputs."""
    for url in urls:
        if not url:
            continue
        masked = mask_url(url)
        if masked != url:
            text = text.replace(url, masked)
    return text
