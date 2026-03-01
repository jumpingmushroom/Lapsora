"""go2rtc integration service."""

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


async def grab_frame(base_url: str, name: str) -> bytes:
    """Grab a JPEG snapshot from go2rtc."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{base_url}/api/frame.jpeg", params={"src": name})
        resp.raise_for_status()
        if not resp.content:
            raise RuntimeError("Empty frame from go2rtc")
        return resp.content


async def test_stream(base_url: str, name: str) -> dict:
    """Test a go2rtc stream by attempting a snapshot."""
    try:
        await grab_frame(base_url, name)
        return {"success": True, "message": "Stream snapshot successful", "details": None}
    except httpx.TimeoutException:
        return {"success": False, "message": "Snapshot timed out", "details": None}
    except Exception as exc:
        return {"success": False, "message": str(exc), "details": None}
