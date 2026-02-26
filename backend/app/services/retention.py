"""Data retention and storage cleanup service."""

import logging
import os
import shutil
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.config import settings
from app.database import SessionLocal
from app.models import Capture, Timelapse

logger = logging.getLogger(__name__)

# Retention periods
CAPTURE_RETENTION_DAYS = 32
DAILY_TIMELAPSE_RETENTION_DAYS = 90
WEEKLY_TIMELAPSE_RETENTION_DAYS = 365
MONTHLY_TIMELAPSE_RETENTION_DAYS = 1825  # 5 years


async def run_retention_cleanup() -> dict:
    """Run all retention cleanup tasks. Returns summary of actions taken."""
    db = SessionLocal()
    summary = {
        "captures_deleted": 0,
        "timelapses_deleted": 0,
        "orphan_records_cleaned": 0,
        "orphan_files_cleaned": 0,
        "empty_dirs_removed": 0,
    }

    try:
        now = datetime.utcnow()

        # 1. Delete old captures
        cutoff = now - timedelta(days=CAPTURE_RETENTION_DAYS)
        old_captures = db.execute(
            select(Capture).where(Capture.captured_at < cutoff)
        ).scalars().all()

        for cap in old_captures:
            if os.path.exists(cap.file_path):
                os.unlink(cap.file_path)
            db.delete(cap)
            summary["captures_deleted"] += 1

        # 2. Delete old timelapses by period type
        timelapse_rules = [
            ("daily", DAILY_TIMELAPSE_RETENTION_DAYS),
            ("weekly", WEEKLY_TIMELAPSE_RETENTION_DAYS),
            ("monthly", MONTHLY_TIMELAPSE_RETENTION_DAYS),
        ]

        for period_type, retention_days in timelapse_rules:
            cutoff = now - timedelta(days=retention_days)
            old_tl = db.execute(
                select(Timelapse).where(
                    Timelapse.period_type == period_type,
                    Timelapse.created_at < cutoff,
                )
            ).scalars().all()

            for tl in old_tl:
                if os.path.exists(tl.file_path):
                    os.unlink(tl.file_path)
                db.delete(tl)
                summary["timelapses_deleted"] += 1

        db.commit()

        # 3. Clean orphaned DB records (file doesn't exist)
        all_captures = db.execute(select(Capture)).scalars().all()
        for cap in all_captures:
            if not os.path.exists(cap.file_path):
                db.delete(cap)
                summary["orphan_records_cleaned"] += 1

        all_timelapses = db.execute(select(Timelapse)).scalars().all()
        for tl in all_timelapses:
            if not os.path.exists(tl.file_path):
                db.delete(tl)
                summary["orphan_records_cleaned"] += 1

        db.commit()

        # 4. Clean orphaned files (no DB record)
        captures_dir = os.path.join(settings.DATA_DIR, "captures")
        if os.path.isdir(captures_dir):
            known_capture_paths = set(
                row[0]
                for row in db.execute(select(Capture.file_path)).all()
            )
            for root, _dirs, files in os.walk(captures_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if fpath not in known_capture_paths:
                        os.unlink(fpath)
                        summary["orphan_files_cleaned"] += 1

        timelapses_dir = os.path.join(settings.DATA_DIR, "timelapses")
        if os.path.isdir(timelapses_dir):
            known_tl_paths = set(
                row[0]
                for row in db.execute(select(Timelapse.file_path)).all()
            )
            for root, _dirs, files in os.walk(timelapses_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if fpath not in known_tl_paths:
                        os.unlink(fpath)
                        summary["orphan_files_cleaned"] += 1

        # 5. Remove empty directories
        for base_dir in [captures_dir, timelapses_dir]:
            if not os.path.isdir(base_dir):
                continue
            for root, dirs, files in os.walk(base_dir, topdown=False):
                if root == base_dir:
                    continue
                if not os.listdir(root):
                    os.rmdir(root)
                    summary["empty_dirs_removed"] += 1

        logger.info("Retention cleanup complete: %s", summary)
        return summary

    finally:
        db.close()


def get_storage_stats() -> dict:
    """Calculate storage usage statistics."""
    db = SessionLocal()
    try:
        # Capture stats
        captures = db.execute(select(Capture)).scalars().all()
        captures_count = len(captures)
        captures_size = sum(c.file_size or 0 for c in captures)

        # Timelapse stats
        timelapses = db.execute(select(Timelapse)).scalars().all()
        timelapses_count = len(timelapses)
        timelapses_size = sum(t.file_size or 0 for t in timelapses)

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
        db.close()
