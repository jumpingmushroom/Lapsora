"""Credential decryption must degrade to a readable error, never a 500.

A regenerated .secret_key (see config._load_or_create_persistent_key) leaves
stored secrets undecryptable. Every read path has to say so rather than raise.
"""

import httpx
import pytest

from app import config
from app.models import Setting
from app.services import homeassistant as ha_service
from app.services import prusalink as prusalink_service


# --- decrypt_optional -------------------------------------------------------

def test_decrypt_optional_round_trips_a_valid_token():
    assert config.decrypt_optional(config.encrypt("hunter2")) == "hunter2"


def test_decrypt_optional_returns_none_for_a_foreign_token(monkeypatch):
    token = config.encrypt("hunter2")
    monkeypatch.setattr(config.settings, "SECRET_KEY", "a-completely-different-key")
    assert config.decrypt_optional(token) is None


def test_decrypt_optional_returns_none_for_garbage():
    assert config.decrypt_optional("not-a-fernet-token") is None


# --- test endpoints ---------------------------------------------------------

def test_prusalink_test_reports_undecryptable_password(client, db, monkeypatch):
    db.add(Setting(key="prusalink_base_url", value="http://printer"))
    db.add(Setting(key="prusalink_password", value=config.encrypt("pw")))
    db.commit()
    monkeypatch.setattr(config.settings, "SECRET_KEY", "rotated-key")

    resp = client.post(
        "/api/settings/prusalink/test",
        json={"base_url": "http://printer", "username": "maker"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "re-enter" in body["message"].lower()


def test_ha_test_reports_undecryptable_token(client, db, monkeypatch):
    db.add(Setting(key="ha_base_url", value="http://ha"))
    db.add(Setting(key="ha_token", value=config.encrypt("tok")))
    db.commit()
    monkeypatch.setattr(config.settings, "SECRET_KEY", "rotated-key")

    resp = client.post("/api/settings/homeassistant/test", json={"base_url": "http://ha"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "re-enter" in body["message"].lower()


# --- absent-credential fallback ---------------------------------------------
#
# The refactor in Step 4/5 restructured `if row and row.value: ... else: token = ""`.
# These tests make sure a missing/empty stored credential still falls through to
# an (empty-credential) connection attempt rather than being mistaken for the
# undecryptable-secret branch. The outbound httpx call is faked (as in
# tests/test_http_source.py) so the "connection attempt" is fast and
# deterministic rather than a real network call against a bogus host.


class _FakeUnreachableClient:
    """Stands in for httpx.AsyncClient; every request looks like a dead host."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        raise httpx.ConnectError("connection refused")


def _patch_unreachable(monkeypatch, module):
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda *a, **k: _FakeUnreachableClient())


def test_prusalink_test_falls_back_when_no_stored_password(client, db, monkeypatch):
    _patch_unreachable(monkeypatch, prusalink_service)

    resp = client.post(
        "/api/settings/prusalink/test",
        json={"base_url": "http://printer", "username": "maker"},
    )

    assert resp.status_code == 200
    message = resp.json()["message"].lower()
    assert "cannot be decrypted" not in message
    assert "re-enter" not in message


def test_prusalink_test_falls_back_when_stored_password_is_empty(client, db, monkeypatch):
    db.add(Setting(key="prusalink_base_url", value="http://printer"))
    db.add(Setting(key="prusalink_password", value=""))
    db.commit()
    _patch_unreachable(monkeypatch, prusalink_service)

    resp = client.post(
        "/api/settings/prusalink/test",
        json={"base_url": "http://printer", "username": "maker"},
    )

    assert resp.status_code == 200
    message = resp.json()["message"].lower()
    assert "cannot be decrypted" not in message
    assert "re-enter" not in message


def test_ha_test_falls_back_when_no_stored_token(client, db, monkeypatch):
    _patch_unreachable(monkeypatch, ha_service)

    resp = client.post("/api/settings/homeassistant/test", json={"base_url": "http://ha"})

    assert resp.status_code == 200
    message = resp.json()["message"].lower()
    assert "cannot be decrypted" not in message
    assert "re-enter" not in message


def test_ha_test_falls_back_when_stored_token_is_empty(client, db, monkeypatch):
    db.add(Setting(key="ha_base_url", value="http://ha"))
    db.add(Setting(key="ha_token", value=""))
    db.commit()
    _patch_unreachable(monkeypatch, ha_service)

    resp = client.post("/api/settings/homeassistant/test", json={"base_url": "http://ha"})

    assert resp.status_code == 200
    message = resp.json()["message"].lower()
    assert "cannot be decrypted" not in message
    assert "re-enter" not in message


# --- credential_error on the read endpoints ---------------------------------

def test_prusalink_read_flags_undecryptable_password(client, db, monkeypatch):
    db.add(Setting(key="prusalink_base_url", value="http://printer"))
    db.add(Setting(key="prusalink_password", value=config.encrypt("pw")))
    db.commit()
    monkeypatch.setattr(config.settings, "SECRET_KEY", "rotated-key")

    body = client.get("/api/settings/prusalink").json()

    assert body["configured"] is True       # a secret IS stored
    assert body["credential_error"] is True  # ...it just can't be read
    assert body["connected"] is False


def test_prusalink_read_clean_when_nothing_configured(client, db):
    body = client.get("/api/settings/prusalink").json()
    assert body["configured"] is False
    assert body["credential_error"] is False


def test_ha_read_flags_undecryptable_token(client, db, monkeypatch):
    db.add(Setting(key="ha_base_url", value="http://ha"))
    db.add(Setting(key="ha_token", value=config.encrypt("tok")))
    db.commit()
    monkeypatch.setattr(config.settings, "SECRET_KEY", "rotated-key")

    body = client.get("/api/settings/homeassistant").json()

    assert body["configured"] is True
    assert body["credential_error"] is True
    assert body["connected"] is False


def test_ha_read_clean_when_nothing_configured(client, db):
    body = client.get("/api/settings/homeassistant").json()
    assert body["configured"] is False
    assert body["credential_error"] is False
