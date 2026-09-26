"""Crash-safe file replacement: readers see the old or the new content, never a torn write."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Replace ``path`` with ``data``; the result is owner-only (``600``) because callers store secrets."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    # .tmp_* is gitignored: a leftover after a crash holds secrets.
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".tmp_{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    # The new content is already in place; failing the caller now would report a write that succeeded.
    try:
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        logger.warning("Could not fsync directory %s: %s", target.parent, exc)


def atomic_write_text(path: Path | str, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))
