"""Move live paths aside while they are replaced, and put them back if the replace fails."""

from __future__ import annotations

import logging
import os
import secrets
import shutil
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


@contextmanager
def stashed(paths: Iterable[Path]) -> Iterator[None]:
    """Rename ``paths`` to hidden siblings (same filesystem, atomic) for the duration of the block.

    If the block raises, whatever it wrote at those paths is removed and the originals return,
    including paths that did not exist before. On success the originals are deleted.
    """
    tag = secrets.token_hex(4)
    moved: list[tuple[Path, Path | None]] = []

    def restore() -> None:
        for path, backup in reversed(moved):
            try:
                _remove(path)
                if backup is not None:
                    os.rename(backup, path)
            except OSError:
                logger.exception("Could not restore %s (saved copy: %s)", path, backup)

    try:
        for path in paths:
            if path.exists() or path.is_symlink():
                backup = path.with_name(f".{path.name}.prev-{tag}")
                os.rename(path, backup)
                moved.append((path, backup))
            else:
                moved.append((path, None))
    except BaseException:
        restore()
        raise

    try:
        yield
    except BaseException:
        restore()
        raise

    for _path, backup in moved:
        if backup is not None:
            try:
                _remove(backup)
            except OSError:
                logger.exception("Could not remove replaced copy %s", backup)
