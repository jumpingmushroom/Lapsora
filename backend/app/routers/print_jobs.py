"""Read API for PrusaLink print history."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PrintJob
from app.schemas import PrintJobRead

router = APIRouter(prefix="/api/print-jobs", tags=["print-jobs"])


@router.get("", response_model=list[PrintJobRead])
def list_print_jobs(limit: int = 100, db: Session = Depends(get_db)):
    return (
        db.query(PrintJob)
        .order_by(PrintJob.id.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
