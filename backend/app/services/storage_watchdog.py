"""Storage write-health watchdog.

The data volume can become unwritable to the app process while reads keep
working — most commonly on Unraid when an appdata backup/restore or a
permissions reset re-chowns ``/app/data`` away from the app user, or when the
underlying filesystem goes briefly read-only. In that state SQLite raises
"attempt to write a readonly database" and ``os.makedirs`` under ``captures/``
raises ``[Errno 13] Permission denied`` — captures silently stop while streams
and previews (read-only paths) appear healthy, so nothing surfaces the outage.

This watchdog actively probes write-ability on an interval and escalates:

  1. transient poisoned DB connections  -> ``engine.dispose()`` + retry
  2. persistent failure (e.g. ownership) -> exit the process so the container
     restart policy recreates it; the entrypoint re-chowns ``/app/data`` to the
     app user on startup, which fixes the ownership case automatically.

Worst case becomes ~one escalation window of downtime followed by automatic
recovery, instead of an indefinite silent stall.
"""

import logging
import os
import tempfile
from datetime import UTC, datetime

from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal, engine

logger = logging.getLogger(__name__)

# Consecutive write-probe failures before we restart the process.
FAILURE_THRESHOLD = 3

_consecutive_failures = 0


def probe_storage_writable() -> tuple[bool, str | None]:
    """Attempt a real write to both the DB and the captures directory.

    Returns ``(True, None)`` on success or ``(False, reason)`` on failure.
    Exercises the two write paths that silently break: the SQLite database
    and ``os.makedirs`` under the captures tree.
    """
    # 1. Database write probe — a dedicated heartbeat table, self-contained so
    #    it needs no model/schema assumptions and leaves no meaningful residue.
    db = SessionLocal()
    try:
        now = datetime.now(UTC).isoformat()
        db.execute(
            text("CREATE TABLE IF NOT EXISTS _storage_probe (id INTEGER PRIMARY KEY, ts TEXT)")
        )
        db.execute(
            text("INSERT OR REPLACE INTO _storage_probe (id, ts) VALUES (1, :ts)"),
            {"ts": now},
        )
        db.commit()
    except Exception as exc:
        return False, f"db write failed: {exc}"
    finally:
        db.rollback()
        db.close()

    # 2. Filesystem write probe — mirror the exact capture operation that
    #    silently broke: creating a *new* directory under captures/. A fresh
    #    temp dir each run tests write-ability of captures/ itself (the real
    #    failure was an inability to create a new date folder), not just write
    #    access inside a pre-existing probe dir.
    captures_dir = os.path.join(settings.DATA_DIR, "captures")
    probe_dir = None
    try:
        os.makedirs(captures_dir, exist_ok=True)
        probe_dir = tempfile.mkdtemp(prefix=".watchdog_probe_", dir=captures_dir)
        probe_file = os.path.join(probe_dir, "probe")
        with open(probe_file, "w") as f:
            f.write("ok")
        os.remove(probe_file)
    except Exception as exc:
        return False, f"captures dir write failed: {exc}"
    finally:
        if probe_dir and os.path.isdir(probe_dir):
            try:
                os.rmdir(probe_dir)
            except OSError:
                pass

    return True, None


async def check_storage_writable() -> None:
    """Watchdog job: probe write-ability and escalate on persistent failure."""
    global _consecutive_failures

    ok, reason = probe_storage_writable()
    if ok:
        if _consecutive_failures:
            logger.info("Storage write recovered after %d failure(s)", _consecutive_failures)
        _consecutive_failures = 0
        return

    _consecutive_failures += 1
    logger.warning(
        "Storage write probe failed (%d/%d): %s",
        _consecutive_failures, FAILURE_THRESHOLD, reason,
    )

    # First line of defence: a transient read-only event may have poisoned the
    # pooled SQLite connections (a read ping still passes, so pool_pre_ping
    # never recycles them). Dropping the pool forces fresh connections next time.
    try:
        engine.dispose()
        logger.info("Disposed DB connection pool to clear any poisoned connections")
    except Exception:
        logger.exception("Failed to dispose DB connection pool")

    if _consecutive_failures >= FAILURE_THRESHOLD:
        logger.critical(
            "Storage unwritable after %d consecutive probes (%s). Exiting so the "
            "container restart policy recreates the process and the entrypoint "
            "re-applies ownership of the data volume.",
            _consecutive_failures, reason,
        )
        # Abrupt exit: we want the container to die and be recreated cleanly.
        # Flush logging handlers first so the CRITICAL line is not lost.
        logging.shutdown()
        os._exit(1)
