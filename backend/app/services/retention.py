"""Data retention and storage cleanup service."""

import logging
import os
import shutil
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.config import settings
from app.database import SessionLocal
from app.models import Capture, Timelapse

logger = logging.getLogger(__name__)


async def run_profile_cleanup(
    profile_id: int,
    capture_retention_days: int,
    timelapse_retention_days: int,
) -> dict:
    """Run cleanup for a specific profile with given retention settings."""
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
            cap_abs = os.path.join(settings.DATA_DIR, cap.file_path)
            if os.path.exists(cap_abs):
                os.unlink(cap_abs)
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
            if os.path.exists(tl_abs):
                os.unlink(tl_abs)
            db.delete(tl)
            summary["timelapses_deleted"] += 1

        db.commit()

        # 3. Clean orphaned DB records for this profile (file doesn't exist).
        # Fetch only the columns needed for the existence check rather than
        # hydrating full ORM rows, and remove orphans in a single DELETE.
        # (The per-row stat is intrinsic to detecting missing files.)
        capture_rows = db.execute(
            select(Capture.id, Capture.file_path).where(Capture.profile_id == profile_id)
        ).all()
        orphan_capture_ids = [
            cid for cid, fpath in capture_rows
            if not os.path.exists(os.path.join(settings.DATA_DIR, fpath))
        ]
        if orphan_capture_ids:
            db.execute(delete(Capture).where(Capture.id.in_(orphan_capture_ids)))
            summary["orphan_records_cleaned"] += len(orphan_capture_ids)

        timelapse_rows = db.execute(
            select(Timelapse.id, Timelapse.file_path).where(Timelapse.profile_id == profile_id)
        ).all()
        orphan_timelapse_ids = [
            tid for tid, fpath in timelapse_rows
            if not os.path.exists(
                fpath if os.path.isabs(fpath) else os.path.join(settings.DATA_DIR, fpath)
            )
        ]
        if orphan_timelapse_ids:
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
                if not os.listdir(root):
                    os.rmdir(root)
                    summary["empty_dirs_removed"] += 1

        logger.info("Profile cleanup complete: %s", summary)

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
            pass

        # Check low disk space
        try:
            usage = shutil.disk_usage(settings.DATA_DIR)
            free_pct = usage.free / usage.total * 100 if usage.total > 0 else 100
            threshold_db = SessionLocal()
            try:
                from app.models import Setting
                row = threshold_db.query(Setting).filter(Setting.key == "health_low_disk_threshold_percent").first()
                threshold = int(row.value) if row else 10
            finally:
                threshold_db.rollback()
                threshold_db.close()

            if free_pct < threshold:
                from app.services.events import emit
                await emit(
                    "low_disk_space",
                    "Low disk space warning",
                    f"Only {free_pct:.1f}% disk space remaining ({usage.free // (1024**3)} GB free of {usage.total // (1024**3)} GB).",
                    level="warning",
                )
        except Exception:
            pass

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
