"""Crash-safe file replacement: readers see the old or the new content, never a torn write."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Replace ``path`` with ``data``; the result is owner-only (``600``) because callers store secrets."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    dir_fd = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def atomic_write_text(path: Path | str, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))
