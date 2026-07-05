"""Home Assistant integration: read sensor entity states via the REST API."""

import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0)
CACHE_TTL = 15  # seconds — dedupe near-simultaneous per-profile captures
# Brief negative cache so an unreachable HA isn't re-probed (blocking up to
# TIMEOUT and logging) on every capture across every profile.
NEG_CACHE_TTL = 30
SENSOR_DOMAINS = ("sensor.", "binary_sensor.")

_cache: dict[str, tuple[float, list[dict] | None]] = {}  # base_url -> (ts, states|None)


def get_ha_config(db) -> tuple[str, str] | None:
    """Return (base_url, decrypted_token) from settings, or None if unset."""
    from app.config import decrypt
    from app.models import Setting

    url_row = db.query(Setting).filter(Setting.key == "ha_base_url").first()
    tok_row = db.query(Setting).filter(Setting.key == "ha_token").first()
    if not url_row or not url_row.value or not tok_row or not tok_row.value:
        return None
    try:
        token = decrypt(tok_row.value)
    except Exception:
        logger.warning("Failed to decrypt HA token")
        return None
    return url_row.value, token


async def get_states(base_url: str, token: str) -> list[dict] | None:
    """Fetch all entity states from HA. Cached briefly per base_url."""
    base = base_url.rstrip("/")
    now = time.time()
    cached = _cache.get(base)
    if cached:
        ts, value = cached
        ttl = CACHE_TTL if value is not None else NEG_CACHE_TTL
        if (now - ts) < ttl:
            return value
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{base}/api/states",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            states = resp.json()
            _cache[base] = (now, states)
            return states
    except Exception as exc:
        logger.warning("Failed to fetch HA states from %s: %s", base, exc)
        _cache[base] = (now, None)
        return None


HEALTH_TIMEOUT = httpx.Timeout(3.0)  # short probe for the settings badge


async def health(base_url: str, token: str) -> bool:
    """Quick reachability + auth probe for the settings status badge."""
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            resp = await client.get(
                f"{base}/api/",
                headers={"Authorization": f"Bearer {token}"},
            )
        return resp.status_code == 200
    except Exception:
        return False


async def test_connection(base_url: str, token: str) -> dict:
    """Validate reachability + auth against HA's /api/ root."""
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{base}/api/",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 200:
            return {"success": True, "message": "Connected"}
        if resp.status_code == 401:
            return {"success": False, "message": "Unauthorized — check the access token"}
        return {"success": False, "message": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


async def list_sensor_entities(base_url: str, token: str) -> list[dict]:
    """Return picker-friendly sensor entities (sorted by friendly name)."""
    states = await get_states(base_url, token)
    if not states:
        return []
    out = []
    for s in states:
        eid = s.get("entity_id", "")
        if not eid.startswith(SENSOR_DOMAINS):
            continue
        attrs = s.get("attributes", {})
        out.append({
            "entity_id": eid,
            "friendly_name": attrs.get("friendly_name", eid),
            "unit": attrs.get("unit_of_measurement", ""),
            "device_class": attrs.get("device_class", ""),
        })
    out.sort(key=lambda e: e["friendly_name"].lower())
    return out


async def read_sensors(base_url: str, token: str, entity_ids: list[str]) -> dict[str, dict]:
    """Read current {value, unit} for each entity_id. Missing entities omitted."""
    states = await get_states(base_url, token)
    if not states:
        return {}
    by_id = {s.get("entity_id"): s for s in states}
    result: dict[str, dict] = {}
    for eid in entity_ids:
        s = by_id.get(eid)
        if not s:
            continue
        attrs = s.get("attributes", {})
        result[eid] = {"value": s.get("state"), "unit": attrs.get("unit_of_measurement", "")}
    return result


def build_sensor_snapshot(sensors_json: str | None, readings: dict[str, dict]) -> str | None:
    """Merge a profile's configured sensors with HA readings into a JSON snapshot
    suitable for storing in captures.sensor_data. Returns None if empty/invalid."""
    if not sensors_json:
        return None
    try:
        sensors = json.loads(sensors_json)
    except (json.JSONDecodeError, TypeError):
        return None
    snapshot: dict[str, dict] = {}
    for s in sensors:
        eid = s.get("entity_id")
        r = readings.get(eid) if eid else None
        if not eid or r is None:
            continue
        snapshot[eid] = {
            "value": r.get("value"),
            "unit": s.get("unit") or r.get("unit") or "",
            "label": s.get("label") or eid,
            "icon": s.get("icon") or "",
        }
    return json.dumps(snapshot) if snapshot else None
