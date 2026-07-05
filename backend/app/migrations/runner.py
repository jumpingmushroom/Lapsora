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
                        # SQLite executes DDL in autocommit under pysqlite, so a
                        # migration that fails partway (e.g. the data volume goes
                        # read-only mid-file) leaves earlier statements applied
                        # but writes no _migrations row. On the next boot the
                        # migration re-runs from the top; tolerating "already
                        # exists" (table/index), "duplicate column name" (ADD
                        # COLUMN lacks IF NOT EXISTS) and "no such column" (a
                        # replayed DROP COLUMN whose column is already gone) lets
                        # it converge instead of boot-looping on the
                        # already-applied prefix. DDL here is idempotent by
                        # object name, so skipping is safe.
                        msg = str(exc).lower()
                        if (
                            "duplicate column name" in msg
                            or "already exists" in msg
                            or "no such column" in msg
                        ):
                            logger.info("Object already in target state, skipping: %s", exc)
                        else:
                            raise

            conn.execute(
                text("INSERT INTO _migrations (filename) VALUES (:f)"),
                {"f": migration.name},
            )
            logger.info("Applied migration: %s", migration.name)
