"""In-memory progress tracker for active timelapse generations."""

from datetime import datetime, timezone

_active_generations: dict[str, dict] = {}


def start_generation(generation_id: str, profile_id: int, steps: list[dict]) -> None:
    """Register a new generation with its step list."""
    for step in steps:
        step.setdefault("status", "pending")
    _active_generations[generation_id] = {
        "generation_id": generation_id,
        "profile_id": profile_id,
        "steps": steps,
        "frame_count": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
    }


def update_step(generation_id: str, step_name: str, status: str) -> dict | None:
    """Mark a step as 'in_progress', 'completed', or 'skipped'. Returns current state."""
    gen = _active_generations.get(generation_id)
    if not gen:
        return None
    for step in gen["steps"]:
        if step["name"] == step_name:
            step["status"] = status
            break
    return gen


def set_frame_count(generation_id: str, count: int) -> None:
    """Set the frame count for a generation."""
    gen = _active_generations.get(generation_id)
    if gen:
        gen["frame_count"] = count


def complete_generation(generation_id: str) -> None:
    """Remove a completed generation from tracking."""
    _active_generations.pop(generation_id, None)


def fail_generation(generation_id: str, error: str) -> None:
    """Mark generation as failed (keeps it briefly for the frontend to see)."""
    gen = _active_generations.get(generation_id)
    if gen:
        gen["status"] = "failed"
        gen["error"] = error
    # Remove after marking - frontend will get the failure via SSE
    _active_generations.pop(generation_id, None)


def cancel_generation(generation_id: str) -> None:
    """Mark generation as cancelled and remove from tracking."""
    gen = _active_generations.get(generation_id)
    if gen:
        gen["status"] = "cancelled"
    _active_generations.pop(generation_id, None)


def get_active_generations() -> list[dict]:
    """Return all active generation states."""
    return list(_active_generations.values())
