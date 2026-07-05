"""Data retention and storage cleanup service."""

import asyncio
import logging
import os
import shutil
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.config import settings
from app.database import SessionLocal
from app.models import Capture, Timelapse

logger = logging.getLogger(__name__)


def _safe_unlink(path: str) -> None:
    """Remove a file, logging (not raising) on failure so one bad file never
    aborts a cleanup pass mid-loop and leaves the DB rows un-deleted."""
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        logger.exception("Failed to remove file %s during cleanup", path)


# Below this many rows, an "all rows orphaned" result is plausibly genuine
# (e.g. a tiny profile whose few files were removed by hand), so the sanity
# guard below does not fire.
_ORPHAN_SWEEP_MIN_ROWS = 5


def _collect_orphans(rows, base_name: str, to_abs, profile_id: int) -> list:
    """Return the ids in ``rows`` (``(id, file_path)`` tuples) whose backing
    file is missing — but only when the filesystem view is trustworthy.

    ``os.path.exists`` returns False on EACCES as well as ENOENT, so a permission
    flap on the media root (a documented failure mode on this deployment, where
    appdata gets re-chowned out from under the app) would make every row look
    orphaned and wipe records whose files are actually still on disk. Guard the
    sweep: skip entirely if the media root is unreadable, or if an implausibly
    large share of rows appear missing at once.
    """
    base_dir = os.path.join(settings.DATA_DIR, base_name)
    if not os.access(base_dir, os.R_OK | os.X_OK):
        logger.error(
            "Skipping %s orphan sweep for profile %d: media root %s is missing "
            "or unreadable", base_name, profile_id, base_dir,
        )
        return []
    orphan_ids = [rid for rid, fpath in rows if not os.path.exists(to_abs(fpath))]
    if rows and len(orphan_ids) == len(rows) and len(rows) >= _ORPHAN_SWEEP_MIN_ROWS:
        logger.error(
            "Skipping %s orphan sweep for profile %d: all %d rows appear "
            "orphaned, which indicates the media tree is inaccessible rather "
            "than genuinely empty", base_name, profile_id, len(rows),
        )
        return []
    return orphan_ids


async def run_profile_cleanup(
    profile_id: int,
    capture_retention_days: int,
    timelapse_retention_days: int,
) -> dict:
    """Run cleanup for a profile, then emit summary/low-disk notifications.

    The blocking work (DB deletes, file unlinks, the empty-dir os.walk) runs in
    a worker thread so a large nightly cleanup can't stall the event loop and
    cause capture jobs to misfire.
    """
    summary = await asyncio.to_thread(
        _run_profile_cleanup_sync,
        profile_id,
        capture_retention_days,
        timelapse_retention_days,
    )

    # Emit retention summary event
    try:
        from app.services.events import emit
        await emit(
            "retention_summary",
            "Cleanup complete",
            f"Profile {profile_id}: deleted {summary['captures_deleted']} captures, "
            f"{summary['timelapses_deleted']} timelapses. "
            f"Cleaned {summary['orphan_records_cleaned']} orphan records.",
        )
    except Exception:
        logger.exception("Failed to emit retention summary event for profile %d", profile_id)

    low = summary.pop("_low_disk", None)
    if low:
        free_pct, free_bytes, total_bytes = low
        try:
            from app.services.events import emit
            await emit(
                "low_disk_space",
                "Low disk space warning",
                f"Only {free_pct:.1f}% disk space remaining "
                f"({free_bytes // (1024**3)} GB free of {total_bytes // (1024**3)} GB).",
                level="warning",
            )
        except Exception:
            logger.exception("Failed to emit low disk space warning")

    return summary


def _run_profile_cleanup_sync(
    profile_id: int,
    capture_retention_days: int,
    timelapse_retention_days: int,
) -> dict:
    """Blocking cleanup body. Creates and uses its own session entirely within
    the calling thread, so it is safe under ``asyncio.to_thread``. Returns the
    summary plus a private ``_low_disk`` tuple for the async caller to emit on."""
    db = SessionLocal()
    summary = {
        "profile_id": profile_id,
        "captures_deleted": 0,
        "timelapses_deleted": 0,
        "orphan_records_cleaned": 0,
        "empty_dirs_removed": 0,
    }

    try:
        now = datetime.now(UTC)

        # 1. Delete old captures for this profile
        cutoff = now - timedelta(days=capture_retention_days)
        old_captures = db.execute(
            select(Capture).where(
                Capture.profile_id == profile_id,
                Capture.captured_at < cutoff,
            )
        ).scalars().all()

        for cap in old_captures:
            _safe_unlink(os.path.join(settings.DATA_DIR, cap.file_path))
            db.delete(cap)
            summary["captures_deleted"] += 1

        # 2. Delete old timelapses for this profile (all period types)
        cutoff = now - timedelta(days=timelapse_retention_days)
        old_tl = db.execute(
            select(Timelapse).where(
                Timelapse.profile_id == profile_id,
                Timelapse.created_at < cutoff,
            )
        ).scalars().all()

        for tl in old_tl:
            tl_abs = tl.file_path if os.path.isabs(tl.file_path) else os.path.join(settings.DATA_DIR, tl.file_path)
            _safe_unlink(tl_abs)
            if tl.thumbnail_path:
                thumb_abs = (
                    tl.thumbnail_path if os.path.isabs(tl.thumbnail_path)
                    else os.path.join(settings.DATA_DIR, tl.thumbnail_path)
                )
                _safe_unlink(thumb_abs)
            db.delete(tl)
            summary["timelapses_deleted"] += 1

        db.commit()

        # 3. Clean orphaned DB records for this profile (file doesn't exist).
        # Fetch only the columns needed for the existence check rather than
        # hydrating full ORM rows, and remove orphans in a single DELETE.
        # (The per-row stat is intrinsic to detecting missing files.)
        # _collect_orphans guards against a permission flap on the media root
        # making every file look missing and wiping the records.
        capture_rows = db.execute(
            select(Capture.id, Capture.file_path).where(Capture.profile_id == profile_id)
        ).all()
        orphan_capture_ids = _collect_orphans(
            capture_rows,
            "captures",
            lambda fp: os.path.join(settings.DATA_DIR, fp),
            profile_id,
        )
        if orphan_capture_ids:
            db.execute(delete(Capture).where(Capture.id.in_(orphan_capture_ids)))
            summary["orphan_records_cleaned"] += len(orphan_capture_ids)

        timelapse_rows = db.execute(
            select(Timelapse.id, Timelapse.file_path, Timelapse.thumbnail_path).where(
                Timelapse.profile_id == profile_id
            )
        ).all()
        orphan_timelapse_ids = _collect_orphans(
            [(tid, fpath) for tid, fpath, _thumb in timelapse_rows],
            "timelapses",
            lambda fp: fp if os.path.isabs(fp) else os.path.join(settings.DATA_DIR, fp),
            profile_id,
        )
        if orphan_timelapse_ids:
            orphan_set = set(orphan_timelapse_ids)
            for tid, _fpath, thumb in timelapse_rows:
                if tid in orphan_set and thumb:
                    thumb_abs = thumb if os.path.isabs(thumb) else os.path.join(settings.DATA_DIR, thumb)
                    _safe_unlink(thumb_abs)
            db.execute(delete(Timelapse).where(Timelapse.id.in_(orphan_timelapse_ids)))
            summary["orphan_records_cleaned"] += len(orphan_timelapse_ids)

        db.commit()

        # 4. Remove empty directories
        for base_name in ["captures", "timelapses"]:
            base_dir = os.path.join(settings.DATA_DIR, base_name)
            if not os.path.isdir(base_dir):
                continue
            for root, dirs, files in os.walk(base_dir, topdown=False):
                if root == base_dir:
                    continue
                # A capture landing between listdir and rmdir raises ENOTEMPTY;
                # skip rather than abort the whole sweep (it self-heals next run).
                try:
                    if not os.listdir(root):
                        os.rmdir(root)
                        summary["empty_dirs_removed"] += 1
                except OSError:
                    logger.debug("Skipping non-empty/locked dir during cleanup: %s", root)

        logger.info("Profile cleanup complete: %s", summary)

        # Determine low-disk state here (cheap stat); the async wrapper emits.
        summary["_low_disk"] = None
        try:
            usage = shutil.disk_usage(settings.DATA_DIR)
            free_pct = usage.free / usage.total * 100 if usage.total > 0 else 100
            from app.models import Setting
            row = db.query(Setting).filter(
                Setting.key == "health_low_disk_threshold_percent"
            ).first()
            threshold = int(row.value) if row else 10
            if free_pct < threshold:
                summary["_low_disk"] = (free_pct, usage.free, usage.total)
        except Exception:
            logger.exception("Failed to check low disk space")

        return summary

    finally:
        db.rollback()
        db.close()


def get_disk_free_bytes() -> int:
    """Free bytes on the data volume, or 0 if unavailable. Cheap (no table
    scans) — prefer this over ``get_storage_stats`` when only free space is
    needed."""
    try:
        return shutil.disk_usage(settings.DATA_DIR).free
    except OSError:
        return 0


def get_storage_stats() -> dict:
    """Calculate storage usage statistics."""
    db = SessionLocal()
    try:
        from sqlalchemy import func

        cap_stats = db.query(
            func.count(Capture.id),
            func.coalesce(func.sum(Capture.file_size), 0),
        ).first()
        captures_count = cap_stats[0]
        captures_size = cap_stats[1]

        tl_stats = db.query(
            func.count(Timelapse.id),
            func.coalesce(func.sum(Timelapse.file_size), 0),
        ).first()
        timelapses_count = tl_stats[0]
        timelapses_size = tl_stats[1]

        total_size = captures_size + timelapses_size

        # Disk usage
        try:
            usage = shutil.disk_usage(settings.DATA_DIR)
            disk_free = usage.free
            disk_total = usage.total
        except OSError:
            disk_free = 0
            disk_total = 0

        return {
            "captures_count": captures_count,
            "captures_size_bytes": captures_size,
            "timelapses_count": timelapses_count,
            "timelapses_size_bytes": timelapses_size,
            "total_size_bytes": total_size,
            "disk_free_bytes": disk_free,
            "disk_total_bytes": disk_total,
        }
    finally:
        db.rollback()
        db.close()
