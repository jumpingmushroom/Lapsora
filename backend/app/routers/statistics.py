"""Statistics endpoints for storage trends and capture activity."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    CaptureActivityPoint,
    ProfileStoragePoint,
    StatsSummary,
    StorageTrendPoint,
)
from app.services.retention import get_storage_stats

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("/summary", response_model=StatsSummary)
def get_summary(db: Session = Depends(get_db)):
    row = db.execute(
        text(
            """
            SELECT
                COUNT(*) AS total,
                MIN(date(captured_at)) AS first_date,
                MAX(date(captured_at)) AS last_date,
                COALESCE(SUM(file_size), 0) AS total_bytes
            FROM captures
            WHERE file_size IS NOT NULL
            """
        )
    ).one()

    total_captures = row.total
    total_bytes = row.total_bytes

    if row.first_date and row.last_date and row.first_date != row.last_date:
        first = date.fromisoformat(row.first_date)
        last = date.fromisoformat(row.last_date)
        span_days = (last - first).days or 1
        avg_captures_per_day = total_captures / span_days
        avg_bytes_per_day = total_bytes / span_days
    elif total_captures > 0:
        avg_captures_per_day = float(total_captures)
        avg_bytes_per_day = float(total_bytes)
    else:
        avg_captures_per_day = 0.0
        avg_bytes_per_day = 0.0

    # Days until full based on 7-day rate
    days_until_full = None
    if avg_bytes_per_day > 0:
        seven_days_ago = (date.today() - timedelta(days=7)).isoformat()
        recent = db.execute(
            text(
                """
                SELECT COALESCE(SUM(file_size), 0) AS bytes_7d
                FROM captures
                WHERE file_size IS NOT NULL AND date(captured_at) >= :cutoff
                """
            ),
            {"cutoff": seven_days_ago},
        ).one()
        # Also count timelapse bytes
        recent_tl = db.execute(
            text(
                """
                SELECT COALESCE(SUM(file_size), 0) AS bytes_7d
                FROM timelapses
                WHERE file_size IS NOT NULL AND date(created_at) >= :cutoff
                """
            ),
            {"cutoff": seven_days_ago},
        ).one()
        total_7d = recent.bytes_7d + recent_tl.bytes_7d
        if total_7d > 0:
            daily_rate = total_7d / 7
            storage = get_storage_stats()
            free = storage["disk_free_bytes"]
            days_until_full = free / daily_rate if daily_rate > 0 else None

    return StatsSummary(
        total_captures=total_captures,
        avg_captures_per_day=round(avg_captures_per_day, 1),
        avg_bytes_per_day=round(avg_bytes_per_day, 1),
        days_until_full=round(days_until_full, 1) if days_until_full is not None else None,
    )


@router.get("/storage-trend", response_model=list[StorageTrendPoint])
def get_storage_trend(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Pre-cutoff totals for anchoring cumulative sum
    pre = db.execute(
        text(
            """
            SELECT COALESCE(SUM(file_size), 0) AS total
            FROM (
                SELECT file_size FROM captures WHERE file_size IS NOT NULL AND date(captured_at) < :cutoff
                UNION ALL
                SELECT file_size FROM timelapses WHERE file_size IS NOT NULL AND date(created_at) < :cutoff
            )
            """
        ),
        {"cutoff": cutoff},
    ).one()
    pre_total = pre.total

    rows = db.execute(
        text(
            """
            SELECT d, SUM(bytes) AS bytes_added
            FROM (
                SELECT date(captured_at) AS d, COALESCE(file_size, 0) AS bytes
                FROM captures WHERE date(captured_at) >= :cutoff AND file_size IS NOT NULL
                UNION ALL
                SELECT date(created_at) AS d, COALESCE(file_size, 0) AS bytes
                FROM timelapses WHERE date(created_at) >= :cutoff AND file_size IS NOT NULL
            )
            GROUP BY d ORDER BY d
            """
        ),
        {"cutoff": cutoff},
    ).all()

    result = []
    cumulative = pre_total
    for row in rows:
        cumulative += row.bytes_added
        result.append(
            StorageTrendPoint(
                date=row.d,
                bytes_added=row.bytes_added,
                cumulative_bytes=cumulative,
            )
        )
    return result


@router.get("/capture-activity", response_model=list[CaptureActivityPoint])
def get_capture_activity(
    days: int = Query(30, ge=1, le=365),
    profile_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    params: dict = {"cutoff": cutoff}

    profile_filter = ""
    if profile_id is not None:
        profile_filter = "AND profile_id = :profile_id"
        params["profile_id"] = profile_id

    rows = db.execute(
        text(
            f"""
            SELECT profile_id, date(captured_at) AS d, COUNT(*) AS cnt
            FROM captures
            WHERE date(captured_at) >= :cutoff {profile_filter}
            GROUP BY profile_id, d
            ORDER BY d
            """
        ),
        params,
    ).all()

    return [
        CaptureActivityPoint(profile_id=r.profile_id, date=r.d, count=r.cnt)
        for r in rows
    ]


@router.get("/profile-storage", response_model=list[ProfileStoragePoint])
def get_profile_storage(
    days: int = Query(30, ge=1, le=365),
    profile_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    params: dict = {"cutoff": cutoff}

    profile_filter = ""
    if profile_id is not None:
        profile_filter = "AND profile_id = :profile_id"
        params["profile_id"] = profile_id

    rows = db.execute(
        text(
            f"""
            SELECT profile_id, date(captured_at) AS d,
                   COALESCE(SUM(file_size), 0) AS bytes,
                   COUNT(*) AS cnt
            FROM captures
            WHERE date(captured_at) >= :cutoff AND file_size IS NOT NULL {profile_filter}
            GROUP BY profile_id, d
            ORDER BY d
            """
        ),
        params,
    ).all()

    return [
        ProfileStoragePoint(profile_id=r.profile_id, date=r.d, bytes=r.bytes, count=r.cnt)
        for r in rows
    ]
