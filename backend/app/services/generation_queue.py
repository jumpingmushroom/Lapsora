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
        # Set the cancel event and leave the job in the asyncio.Queue. The
        # worker checks the event when it dequeues and skips the job (and pops
        # the event) then. Draining/re-enqueuing here would race the worker's
        # get() and double-count task_done() on re-enqueued items, so we don't.
        event = _cancel_events.get(generation_id)
        if event:
            event.set()

        _broadcast_cancelled(generation_id)
        _broadcast_queue_updated()
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
        # The whole iteration body is guarded: a failure in dequeue bookkeeping
        # or SSE broadcast must not kill the worker loop (which would silently
        # hang every future generation). task_done() runs exactly once per get().
        try:
            generation_id = job["generation_id"]

            # Check if already cancelled before starting
            event = _cancel_events.get(generation_id)
            if event and event.is_set():
                with _pending_lock:
                    _pending_jobs[:] = [j for j in _pending_jobs if j["generation_id"] != generation_id]
                _broadcast_queue_updated()
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
        except Exception:
            logger.exception("Queue worker iteration crashed; continuing")
        finally:
            _current_job = None
            gid = job.get("generation_id") if isinstance(job, dict) else None
            if gid:
                _cancel_events.pop(gid, None)
            set_active_ffmpeg_proc(None)
            _queue.task_done()


def _on_worker_done(task: asyncio.Task) -> None:
    """Surface an unexpected worker exit. Previously the task had no callback, so
    if the loop ever died every future generation hung silently. We log loudly
    rather than auto-restart: a restart that immediately re-fails would spin."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Generation queue worker exited unexpectedly; queued generations "
            "will not run until the app restarts",
            exc_info=exc,
        )


def start_worker() -> None:
    """Start the queue worker coroutine. Call from app lifespan."""
    global _worker_task
    _worker_task = asyncio.get_running_loop().create_task(_worker())
    _worker_task.add_done_callback(_on_worker_done)
    logger.info("Generation queue worker launched")


async def stop_worker() -> None:
    """Kill any in-flight ffmpeg and cancel the worker task. Call from app
    lifespan shutdown so a restart mid-render doesn't orphan an ffmpeg process
    or emit 'Task was destroyed but it is pending' warnings."""
    global _worker_task
    proc = get_active_ffmpeg_proc()
    if proc:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    task = _worker_task
    _worker_task = None
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Generation queue worker raised during shutdown")
    logger.info("Generation queue worker stopped")
