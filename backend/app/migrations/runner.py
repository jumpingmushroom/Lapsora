"""Simple SQL migration runner."""

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

VERSIONS_DIR = Path(__file__).parent / "versions"


def run_migrations(engine: Engine) -> None:
    """Apply all unapplied SQL migrations in order."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS _migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL UNIQUE,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        applied = {
            row[0]
            for row in conn.execute(text("SELECT filename FROM _migrations")).fetchall()
        }

        migration_files = sorted(VERSIONS_DIR.glob("*.sql"))

        for migration in migration_files:
            if migration.name in applied:
                continue

            logger.info("Applying migration: %s", migration.name)
            sql = migration.read_text()

            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    try:
                        conn.execute(text(statement))
                    except Exception as exc:
                        # SQLite doesn't support IF NOT EXISTS on ALTER TABLE;
                        # safely skip duplicate column errors
                        if "duplicate column name" in str(exc):
                            logger.info("Column already exists, skipping: %s", exc)
                        else:
                            raise

            conn.execute(
                text("INSERT INTO _migrations (filename) VALUES (:f)"),
                {"f": migration.name},
            )
            logger.info("Applied migration: %s", migration.name)
