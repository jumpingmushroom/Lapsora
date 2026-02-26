"""System health and info endpoints."""

from fastapi import APIRouter

from app.services.retention import get_storage_stats

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@router.get("/storage")
def storage():
    return get_storage_stats()
