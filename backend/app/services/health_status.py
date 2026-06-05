"""Tiny TTL cache for integration reachability badges.

The Settings page shows a live "Connected / Unreachable" badge per integration
(Home Assistant, go2rtc, PrusaLink). Probing the remote on every page load is
wasteful, so each integration's result is cached for CACHE_TTL and invalidated
explicitly when its config is saved. The "Test Connection" buttons stay live
(they hit the remote directly) for users actively debugging a connection.
"""

import time
from collections.abc import Awaitable, Callable

CACHE_TTL = 60.0  # seconds

_cache: dict[str, tuple[float, bool]] = {}  # key -> (monotonic ts, reachable)


async def reachable(key: str, probe: Callable[[], Awaitable[bool]], ttl: float = CACHE_TTL) -> bool:
    """Return a cached reachability result, probing at most once per `ttl`."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    result = bool(await probe())
    _cache[key] = (now, result)
    return result


def invalidate(key: str) -> None:
    """Drop a cached result so the next read re-probes (call after saving config)."""
    _cache.pop(key, None)
