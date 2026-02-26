"""RTSP stream interaction via ffmpeg/ffprobe subprocesses."""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


async def test_connection(url: str) -> dict:
    """Validate an RTSP URL using ffprobe. Returns status and stream details."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-rtsp_transport", "tcp",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode != 0:
            return {
                "success": False,
                "message": f"Connection failed: {stderr.decode().strip() or 'unknown error'}",
                "details": None,
            }

        probe = json.loads(stdout.decode())
        video_streams = [
            s for s in probe.get("streams", []) if s.get("codec_type") == "video"
        ]

        if not video_streams:
            return {
                "success": True,
                "message": "Connected but no video stream found",
                "details": None,
            }

        vs = video_streams[0]
        details = {
            "codec": vs.get("codec_name"),
            "resolution": f"{vs.get('width', '?')}x{vs.get('height', '?')}",
            "fps": vs.get("r_frame_rate"),
        }
        return {"success": True, "message": "Connection successful", "details": details}

    except asyncio.TimeoutError:
        return {"success": False, "message": "Connection timed out after 10s", "details": None}
    except FileNotFoundError:
        return {"success": False, "message": "ffprobe not found; install ffmpeg", "details": None}
    except Exception as exc:
        logger.exception("RTSP test_connection error")
        return {"success": False, "message": str(exc), "details": None}


async def grab_frame(url: str) -> bytes:
    """Grab a single JPEG frame from an RTSP stream using ffmpeg."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", url,
        "-frames:v", "1",
        "-f", "image2",
        "-c:v", "mjpeg",
        "-q:v", "2",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)

    if proc.returncode != 0 or not stdout:
        raise RuntimeError(
            f"Failed to grab frame: {stderr.decode().strip() or 'unknown error'}"
        )

    return stdout
