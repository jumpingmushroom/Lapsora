"""Credential redaction for URLs before they reach logs/notifications (F-16)."""

from app.url_utils import mask_url, scrub_urls


def test_mask_url_redacts_password():
    assert mask_url("rtsp://user:secret@cam.local:554/stream") == "rtsp://user:•••@cam.local:554/stream"


def test_mask_url_leaves_credential_free_url_untouched():
    assert mask_url("http://cam.local/snapshot.jpg") == "http://cam.local/snapshot.jpg"


def test_mask_url_never_raises_on_garbage():
    assert mask_url("not a url") == "not a url"


def test_scrub_urls_replaces_credentials_in_stderr():
    url = "rtsp://admin:hunter2@10.0.0.5/h264"
    stderr = f"[rtsp @ 0x...] method DESCRIBE failed for {url}: 401 Unauthorized"
    out = scrub_urls(stderr, url)
    assert "hunter2" not in out
    assert "rtsp://admin:•••@10.0.0.5/h264" in out


def test_scrub_urls_noop_without_password():
    stderr = "some error about http://cam.local/x"
    assert scrub_urls(stderr, "http://cam.local/x") == stderr
