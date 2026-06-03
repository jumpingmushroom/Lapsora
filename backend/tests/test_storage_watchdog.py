"""Tests for the storage write-health watchdog."""

import os

import pytest
from unittest.mock import patch

from app.services import storage_watchdog


@pytest.fixture(autouse=True)
def reset_counter():
    storage_watchdog._consecutive_failures = 0
    yield
    storage_watchdog._consecutive_failures = 0


@pytest.mark.asyncio
async def test_success_resets_counter():
    storage_watchdog._consecutive_failures = 2
    with patch.object(storage_watchdog, "probe_storage_writable", return_value=(True, None)), \
         patch.object(storage_watchdog.os, "_exit") as exit_mock:
        await storage_watchdog.check_storage_writable()
    assert storage_watchdog._consecutive_failures == 0
    exit_mock.assert_not_called()


@pytest.mark.asyncio
async def test_does_not_exit_before_threshold():
    with patch.object(storage_watchdog, "probe_storage_writable", return_value=(False, "boom")), \
         patch.object(storage_watchdog.engine, "dispose") as dispose_mock, \
         patch.object(storage_watchdog.os, "_exit") as exit_mock:
        for _ in range(storage_watchdog.FAILURE_THRESHOLD - 1):
            await storage_watchdog.check_storage_writable()
        exit_mock.assert_not_called()
        # Pool is disposed on every failure to clear poisoned connections.
        assert dispose_mock.call_count == storage_watchdog.FAILURE_THRESHOLD - 1


@pytest.mark.asyncio
async def test_exits_after_threshold():
    with patch.object(storage_watchdog, "probe_storage_writable", return_value=(False, "boom")), \
         patch.object(storage_watchdog.engine, "dispose"), \
         patch.object(storage_watchdog, "logging"), \
         patch.object(storage_watchdog.os, "_exit") as exit_mock:
        for _ in range(storage_watchdog.FAILURE_THRESHOLD):
            await storage_watchdog.check_storage_writable()
        exit_mock.assert_called_once_with(1)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permission checks")
def test_probe_detects_unwritable_captures(tmp_path, monkeypatch):
    """A captures/ directory the process cannot write to must be reported."""
    data_dir = tmp_path / "data"
    captures = data_dir / "captures"
    captures.mkdir(parents=True)
    # Point the watchdog's DB write at a throwaway sqlite file in the tmp dir.
    db_path = data_dir / "probe.db"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(storage_watchdog, "SessionLocal", sessionmaker(bind=test_engine))
    monkeypatch.setattr(storage_watchdog.settings, "DATA_DIR", str(data_dir))

    ok, _ = storage_watchdog.probe_storage_writable()
    assert ok is True

    # Remove write permission on captures/ → mkdir of a new dir must fail.
    os.chmod(captures, 0o555)
    try:
        ok, reason = storage_watchdog.probe_storage_writable()
        assert ok is False
        assert "captures dir write failed" in reason
    finally:
        os.chmod(captures, 0o755)
