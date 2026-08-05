"""Filesystem helpers shared by the routers that delete media."""

import logging
import os

logger = logging.getLogger(__name__)


def safe_remove(path: str | None) -> None:
    """Remove a file, logging (not raising) on failure so a single bad file
    never aborts a delete that must still purge the DB rows.

    Tolerates None so callers can pass optional columns (thumbnails) directly."""
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.unlink(path)
    except OSError:
        logger.exception("Failed to remove file %s during delete", path)
