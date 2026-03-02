"""System health and info endpoints."""

from fastapi import APIRouter

from app.services.gpu import detect_nvidia_gpu, get_nvenc_encoders, is_nvenc_available, is_cupy_available
from app.services.generation_progress import get_active_generations
from app.services.retention import get_storage_stats

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@router.get("/storage")
def storage():
    return get_storage_stats()


@router.get("/generations/active")
def active_generations():
    return get_active_generations()


@router.get("/system/info")
def system_info():
    gpu = detect_nvidia_gpu()
    encoders = get_nvenc_encoders() if gpu else {}
    return {
        "status": "ok",
        "version": "0.1.0",
        "gpu_available": gpu,
        "nvenc_available": is_nvenc_available(),
        "nvenc_encoders": list(encoders.values()),
        "cupy_available": is_cupy_available(),
    }
