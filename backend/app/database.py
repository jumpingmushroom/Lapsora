"""Database engine and session management."""

import sqlite3
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """SQLite ignores FOREIGN KEY constraints unless foreign_keys=ON is set per
    connection. Without it, the ON DELETE CASCADE clauses in the schema are
    dead and a raw/bulk delete can orphan child rows. Listening on the base
    Engine applies this to every SQLite engine (app and tests)."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # Writers are concurrent (sync routers in FastAPI's threadpool, the
        # AsyncIOScheduler capture/cleanup jobs, the generation worker) against
        # one file DB. WAL lets readers proceed during a write, and busy_timeout
        # makes a blocked writer wait for the lock instead of failing
        # immediately with "database is locked". Both are no-ops on the
        # in-memory test engine.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
