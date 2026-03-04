"""In-memory generation queue enforcing one-at-a-time timelapse generation."""

import asyncio
import json
import logging
import threading
import uuid

logger = logging.getLogger(__name__)

_queue: asyncio.Queue = asyncio.Queue()
_pending_jobs: list[dict] = []
_pending_lock = threading.Lock()
_current_job: dict | None = None
_worker_task: asyncio.Task | None = None

# Cancellation infrastructure
_cancel_events: dict[str, threading.Event] = {}
_active_ffmpeg_proc: asyncio.subprocess.Process | None = None
_ffmpeg_lock = threading.Lock()


def set_active_ffmpeg_proc(proc: asyncio.subprocess.Process | None) -> None:
    """Set (or clear) the reference to the running ffmpeg subprocess."""
    global _active_ffmpeg_proc
    with _ffmpeg_lock:
        _active_ffmpeg_proc = proc


def get_active_ffmpeg_proc() -> asyncio.subprocess.Process | None:
    """Get the currently running ffmpeg subprocess, if any."""
    with _ffmpeg_lock:
        return _active_ffmpeg_proc


def get_cancel_event(generation_id: str) -> threading.Event | None:
    """Get the cancel event for a generation."""
    return _cancel_events.get(generation_id)


async def enqueue_generation(**kwargs) -> dict:
    """Enqueue a timelapse generation job. Returns dict with generation_id and position."""
    generation_id = uuid.uuid4().hex[:12]
    job = {"generation_id": generation_id, **kwargs}

    # Create cancel event for this job
    _cancel_events[generation_id] = threading.Event()

    with _pending_lock:
        _pending_jobs.append(job)
        position = len(_pending_jobs)

    await _queue.put(job)

    # Emit SSE event
    from app.services.notifications import sse_queues, _sse_lock
    sse_data = json.dumps({
        "event_type": "timelapse_queued",
        "generation_id": generation_id,
        "profile_id": kwargs.get("profile_id"),
        "position": position,
    })
    with _sse_lock:
        queues = list(sse_queues)
    for q in queues:
        try:
            q.put_nowait(sse_data)
        except asyncio.QueueFull:
            pass

    logger.info("Enqueued generation %s at position %d", generation_id, position)
    return {"generation_id": generation_id, "position": position}


def get_queue_status() -> list[dict]:
    """Return pending jobs with their queue positions."""
    with _pending_lock:
        return [
            {
                "generation_id": job["generation_id"],
                "profile_id": job.get("profile_id"),
                "position": i + 1,
            }
            for i, job in enumerate(_pending_jobs)
        ]


def _broadcast_queue_updated() -> None:
    """Broadcast updated queue positions to SSE clients."""
    from app.services.notifications import sse_queues, _sse_lock

    status = get_queue_status()
    sse_data = json.dumps({
        "event_type": "timelapse_queue_updated",
        "queue": status,
    })
    with _sse_lock:
        queues = list(sse_queues)
    for q in queues:
        try:
            q.put_nowait(sse_data)
        except asyncio.QueueFull:
            pass


def _broadcast_cancelled(generation_id: str) -> None:
    """Broadcast a timelapse_cancelled SSE event."""
    from app.services.notifications import sse_queues, _sse_lock

    sse_data = json.dumps({
        "event_type": "timelapse_cancelled",
        "generation_id": generation_id,
    })
    with _sse_lock:
        queues = list(sse_queues)
    for q in queues:
        try:
            q.put_nowait(sse_data)
        except asyncio.QueueFull:
            pass


def cancel_generation(generation_id: str) -> bool:
    """Cancel a queued or active generation. Returns True if found."""
    # Check if it's a pending (queued) job
    with _pending_lock:
        found_pending = any(j["generation_id"] == generation_id for j in _pending_jobs)
        if found_pending:
            _pending_jobs[:] = [j for j in _pending_jobs if j["generation_id"] != generation_id]

    if found_pending:
        # Set cancel event so worker skips it when dequeued
        event = _cancel_events.get(generation_id)
        if event:
            event.set()

        # Drain queue and re-enqueue non-cancelled items
        items = []
        while not _queue.empty():
            try:
                items.append(_queue.get_nowait())
                _queue.task_done()
            except asyncio.QueueEmpty:
                break
        for item in items:
            if item["generation_id"] != generation_id:
                _queue.put_nowait(item)

        _broadcast_cancelled(generation_id)
        _broadcast_queue_updated()
        _cancel_events.pop(generation_id, None)
        logger.info("Cancelled queued generation %s", generation_id)
        return True

    # Check if it's the active job
    if _current_job and _current_job["generation_id"] == generation_id:
        event = _cancel_events.get(generation_id)
        if event:
            event.set()
        # Kill ffmpeg if running
        proc = get_active_ffmpeg_proc()
        if proc:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        logger.info("Cancelling active generation %s", generation_id)
        return True

    return False


async def _worker() -> None:
    """Process generation jobs one at a time."""
    global _current_job
    from app.services.timelapse import generate_timelapse

    logger.info("Queue worker started")
    while True:
        job = await _queue.get()
        generation_id = job["generation_id"]

        # Check if already cancelled before starting
        event = _cancel_events.get(generation_id)
        if event and event.is_set():
            _cancel_events.pop(generation_id, None)
            with _pending_lock:
                _pending_jobs[:] = [j for j in _pending_jobs if j["generation_id"] != generation_id]
            _broadcast_queue_updated()
            _queue.task_done()
            continue

        _current_job = job

        # Remove from pending list and broadcast position updates
        with _pending_lock:
            _pending_jobs[:] = [j for j in _pending_jobs if j["generation_id"] != generation_id]
        _broadcast_queue_updated()

        try:
            job_kwargs = {k: v for k, v in job.items() if k != "generation_id"}
            await generate_timelapse(**job_kwargs, cancel_event=event, generation_id=generation_id)
        except Exception:
            logger.exception("Queued generation %s failed", generation_id)
        finally:
            _current_job = None
            _cancel_events.pop(generation_id, None)
            set_active_ffmpeg_proc(None)
            _queue.task_done()


def start_worker() -> None:
    """Start the queue worker coroutine. Call from app lifespan."""
    global _worker_task
    _worker_task = asyncio.get_event_loop().create_task(_worker())
    logger.info("Generation queue worker launched")
