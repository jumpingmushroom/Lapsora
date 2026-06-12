"""Generation-queue cancellation logic.

Guards the cancel-race fix: cancelling a pending job sets its cancel event and
removes it from the visible queue, but does NOT drain the asyncio.Queue or pop
the event — the worker skips and cleans up the job when it dequeues it. This
avoids racing the worker's get() and double-counting task_done().
"""

import threading

from app.services import generation_queue as gq


def _reset() -> None:
    gq._pending_jobs.clear()
    gq._cancel_events.clear()
    gq._current_job = None


def test_cancel_pending_sets_event_and_hides_from_status():
    _reset()
    gid = "pending123"
    gq._pending_jobs.append({"generation_id": gid, "profile_id": 1})
    gq._cancel_events[gid] = threading.Event()

    assert any(j["generation_id"] == gid for j in gq.get_queue_status())

    assert gq.cancel_generation(gid) is True
    # Worker will see the set event on dequeue and skip the job.
    assert gq._cancel_events[gid].is_set()
    # Removed from the user-visible queue.
    assert gq.get_queue_status() == []
    # Event is intentionally NOT popped here — the worker pops it when it skips.
    assert gid in gq._cancel_events
    _reset()


def test_cancel_unknown_generation_returns_false():
    _reset()
    assert gq.cancel_generation("does-not-exist") is False
    _reset()


def test_cancel_active_job_sets_event():
    _reset()
    gid = "active123"
    event = threading.Event()
    gq._cancel_events[gid] = event
    gq._current_job = {"generation_id": gid, "profile_id": 1}

    assert gq.cancel_generation(gid) is True
    assert event.is_set()
    _reset()
