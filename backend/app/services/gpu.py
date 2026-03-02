"""NVIDIA GPU detection and NVENC encoder availability."""

import logging
import subprocess

logger = logging.getLogger(__name__)

_gpu_available: bool | None = None
_nvenc_encoders: dict[str, str] | None = None
_cupy_available: bool | None = None


def detect_nvidia_gpu() -> bool:
    """Check if an NVIDIA GPU is available via nvidia-smi."""
    global _gpu_available
    if _gpu_available is not None:
        return _gpu_available
    try:
        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, timeout=5
        )
        _gpu_available = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _gpu_available = False
    logger.info("NVIDIA GPU detected: %s", _gpu_available)
    return _gpu_available


def get_nvenc_encoders() -> dict[str, str]:
    """Check which NVENC encoders are available in FFmpeg.

    Returns a dict like {"h264": "h264_nvenc", "h265": "hevc_nvenc"}.
    """
    global _nvenc_encoders
    if _nvenc_encoders is not None:
        return _nvenc_encoders
    _nvenc_encoders = {}
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            output = result.stdout
            if "h264_nvenc" in output:
                _nvenc_encoders["h264"] = "h264_nvenc"
            if "hevc_nvenc" in output:
                _nvenc_encoders["h265"] = "hevc_nvenc"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    logger.info("NVENC encoders available: %s", _nvenc_encoders)
    return _nvenc_encoders


def is_nvenc_available() -> bool:
    """True if GPU is detected AND at least one NVENC encoder is present."""
    return detect_nvidia_gpu() and len(get_nvenc_encoders()) > 0


def is_cupy_available() -> bool:
    """Check if CuPy is installed and a CUDA GPU is accessible."""
    global _cupy_available
    if _cupy_available is not None:
        return _cupy_available
    try:
        import cupy as cp
        cp.cuda.runtime.getDeviceCount()
        _cupy_available = True
    except Exception:
        _cupy_available = False
    logger.info("CuPy GPU compute available: %s", _cupy_available)
    return _cupy_available
