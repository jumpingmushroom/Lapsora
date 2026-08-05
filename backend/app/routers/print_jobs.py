"""Read + delete API for PrusaLink print history."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PrintJob, Timelapse
from app.schemas import PrintJobRead
from app.services.files import safe_remove

router = APIRouter(prefix="/api/print-jobs", tags=["print-jobs"])


@router.get("", response_model=list[PrintJobRead])
def list_print_jobs(limit: int = 100, db: Session = Depends(get_db)):
    return (
        db.query(PrintJob)
        .order_by(PrintJob.id.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )


@router.delete("/{print_job_id}", status_code=204)
def delete_print_job(
    print_job_id: int,
    delete_timelapse: bool = False,
    db: Session = Depends(get_db),
):
    """Remove a print-history row, optionally with its rendered timelapse.

    Refuses while the print is still running: the managed capture profile is
    closed out by the reconcile loop keyed on this row, so deleting it would
    leave the profile enabled with nothing left to ever disable it."""
    pj = db.get(PrintJob, print_job_id)
    if not pj:
        raise HTTPException(404, "Print job not found")
    if pj.status == "printing":
        raise HTTPException(409, "Cannot delete a print that is still running")

    paths: list[str | None] = []
    if delete_timelapse and pj.timelapse_id:
        tl = db.get(Timelapse, pj.timelapse_id)
        if tl:
            paths = [tl.file_path, tl.thumbnail_path]
            db.delete(tl)

    db.delete(pj)
    # Commit row removal before unlinking so a failed commit can't leave the
    # media gone but the row (and its 404-ing endpoints) behind.
    db.commit()
    for path in paths:
        safe_remove(path)
