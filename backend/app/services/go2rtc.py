"""go2rtc integration service."""

import asyncio
import logging

import httpx

from app.database import SessionLocal
from app.models import Setting

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0)


def get_go2rtc_url(db) -> str | None:
    row = db.query(Setting).filter(Setting.key == "go2rtc_url").first()
    return row.value if row else None


async def test_server(base_url: str) -> dict:
    """Verify go2rtc server is reachable."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"{base_url}/api/streams")
            resp.raise_for_status()
            return {"success": True, "message": "go2rtc server is reachable"}
    except httpx.TimeoutException:
        return {"success": False, "message": "Connection timed out"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


async def list_streams(base_url: str) -> list[dict]:
    """Fetch available streams from go2rtc."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{base_url}/api/streams")
        resp.raise_for_status()
        data = resp.json()
        # go2rtc returns {name: {producers: [...]}}
        result = []
        for name, info in data.items():
            producers = info.get("producers", []) if isinstance(info, dict) else []
            result.append({"name": name, "producers": producers})
        return result


async def grab_frame(base_url: str, name: str, retries: int = 3) -> bytes:
    """Grab a JPEG snapshot from go2rtc with retry on 5xx errors."""
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for attempt in range(1, retries + 1):
            resp = await client.get(f"{base_url}/api/frame.jpeg", params={"src": name})
            if resp.status_code >= 500 and attempt < retries:
                logger.warning(
                    "go2rtc returned %s for stream %r (attempt %d/%d), retrying...",
                    resp.status_code, name, attempt, retries,
                )
                await asyncio.sleep(1)
                continue
            resp.raise_for_status()
            if not resp.content:
                raise RuntimeError("Empty frame from go2rtc")
            return resp.content
    raise last_exc or RuntimeError("grab_frame exhausted retries")


async def test_stream(base_url: str, name: str) -> dict:
    """Test a go2rtc stream by attempting a snapshot."""
    try:
        await grab_frame(base_url, name)
        return {"success": True, "message": "Stream snapshot successful", "details": None}
    except httpx.TimeoutException:
        return {"success": False, "message": "Snapshot timed out", "details": None}
    except Exception as exc:
        return {"success": False, "message": str(exc), "details": None}
