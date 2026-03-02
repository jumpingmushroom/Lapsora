"""Lapsora FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings as app_settings
from app.database import SessionLocal, engine
from app.migrations.runner import run_migrations
from app.routers import captures, cleanup_schedules, notifications, profile_templates, profiles, settings as settings_router, statistics, streams, system, timelapse_schedules, timelapses

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create data directories
    data_dir = Path(app_settings.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "captures").mkdir(exist_ok=True)
    (data_dir / "timelapses").mkdir(exist_ok=True)

    # Run database migrations
    run_migrations(engine)
    logger.info("Migrations complete, Lapsora starting")

    # Start capture scheduler and restore jobs
    from app.services.scheduler import (
        init_scheduler, restore_jobs,
        add_health_check_job, add_capture_gap_job, scheduler as _scheduler,
    )
    from app.services.events import on_event
    from app.services.notifications import handle_event

    on_event(handle_event)

    init_scheduler()
    db = SessionLocal()
    try:
        restore_jobs(db)
        # Load health check interval from settings
        from app.models import Setting
        row = db.query(Setting).filter(Setting.key == "health_check_interval_seconds").first()
        health_interval = int(row.value) if row else 300
        # Capture gap alerting
        gap_row = db.query(Setting).filter(Setting.key == "capture_gap_enabled").first()
        gap_enabled = not gap_row or gap_row.value != "false"
    finally:
        db.close()
    add_health_check_job(health_interval)
    if gap_enabled:
        add_capture_gap_job()

    yield

    # Shutdown scheduler
    _scheduler.shutdown()


app = FastAPI(title="Lapsora", version="0.1.0", lifespan=lifespan)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(system.router)
app.include_router(streams.router)
app.include_router(profiles.router)
app.include_router(profile_templates.router)
app.include_router(captures.router)
app.include_router(timelapses.router)
app.include_router(timelapse_schedules.router)
app.include_router(cleanup_schedules.router)
app.include_router(notifications.router)
app.include_router(settings_router.router)
app.include_router(statistics.router)

# Static file mounts
data_dir = Path(app_settings.DATA_DIR)
data_dir.mkdir(parents=True, exist_ok=True)
captures_dir = data_dir / "captures"
captures_dir.mkdir(exist_ok=True)
app.mount("/static/captures", StaticFiles(directory=str(captures_dir)), name="static_captures")

timelapses_dir = data_dir / "timelapses"
timelapses_dir.mkdir(exist_ok=True)
app.mount("/static/timelapses", StaticFiles(directory=str(timelapses_dir)), name="static_timelapses")

# Serve frontend build if it exists (SPA with fallback)
_candidates = [
    Path(__file__).parent.parent / "frontend" / "build",      # Docker: /app/frontend/build
    Path(__file__).parent.parent.parent / "frontend" / "build",  # Dev: backend/../frontend/build
]
_frontend_dir: Path | None = None
for _d in _candidates:
    if _d.is_dir():
        _frontend_dir = _d
        break

if _frontend_dir:
    # Serve static assets (JS, CSS, etc.)
    app.mount("/_app", StaticFiles(directory=str(_frontend_dir / "_app")), name="frontend_assets")

    # SPA fallback: serve index.html for all non-API routes
    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        file_path = _frontend_dir / path
        if not file_path.resolve().is_relative_to(_frontend_dir.resolve()):
            return FileResponse(str(_frontend_dir / "index.html"))
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_dir / "index.html"))
