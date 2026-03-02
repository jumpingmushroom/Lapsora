"""Minimal async event bus for decoupled notification delivery."""

import logging
from typing import Callable, Coroutine, Any

logger = logging.getLogger(__name__)

_listeners: list[Callable[..., Coroutine[Any, Any, None]]] = []


def on_event(callback: Callable[..., Coroutine[Any, Any, None]]) -> None:
    """Register an async callback for all events."""
    _listeners.append(callback)


async def emit(event_type: str, title: str, body: str, level: str = "info", data: dict | None = None) -> None:
    """Emit an event to all registered listeners."""
    for listener in _listeners:
        try:
            await listener(event_type, title, body, level, data)
        except Exception:
            logger.exception("Event listener failed for %s", event_type)
