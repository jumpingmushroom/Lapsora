"""Lapsora FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import SessionLocal, engine
from app.migrations.runner import run_migrations
from app.routers import captures, profiles, streams, system, timelapses

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create data directories
    data_dir = Path(settings.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "captures").mkdir(exist_ok=True)
    (data_dir / "timelapses").mkdir(exist_ok=True)

    # Run database migrations
    run_migrations(engine)
    logger.info("Migrations complete, Lapsora starting")

    # Start capture scheduler and restore jobs
    from app.services.scheduler import (
        init_scheduler, restore_jobs, add_scheduled_timelapse_jobs,
        add_retention_job, scheduler as _scheduler,
    )

    init_scheduler()
    db = SessionLocal()
    try:
        restore_jobs(db)
    finally:
        db.close()
    add_scheduled_timelapse_jobs()
    add_retention_job()

    yield

    # Shutdown scheduler
    _scheduler.shutdown()


app = FastAPI(title="Lapsora", version="0.1.0", lifespan=lifespan)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(system.router)
app.include_router(streams.router)
app.include_router(profiles.router)
app.include_router(captures.router)
app.include_router(timelapses.router)

# Static file mounts
data_dir = Path(settings.DATA_DIR)
data_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(data_dir)), name="static")

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
        # Try serving the exact file first
        file_path = _frontend_dir / path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # Fall back to index.html for SPA routing
        return FileResponse(str(_frontend_dir / "index.html"))
