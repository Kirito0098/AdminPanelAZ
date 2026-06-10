"""One-time migration for CIDR list files written to the wrong path before paths.py fix."""

import logging
import shutil
from pathlib import Path

from app.paths import BACKEND_ROOT, get_cidr_list_dir

logger = logging.getLogger(__name__)

_LEGACY_LIST_DIR = BACKEND_ROOT / "app" / "data" / "cidr" / "list"


def migrate_legacy_cidr_list_dir() -> int:
    """Copy *.txt from backend/app/data/cidr/list into backend/data/cidr/list if needed."""
    target_dir = get_cidr_list_dir()
    legacy_dir = _LEGACY_LIST_DIR
    if not legacy_dir.is_dir():
        return 0

    target_dir.mkdir(parents=True, exist_ok=True)
    legacy_files = sorted(
        path for path in legacy_dir.glob("*.txt") if path.is_file()
    )
    if not legacy_files:
        return 0

    migrated = 0
    for legacy_path in legacy_files:
        target_path = target_dir / legacy_path.name
        if target_path.exists():
            continue
        try:
            shutil.copy2(legacy_path, target_path)
            migrated += 1
        except OSError as exc:
            logger.warning("Failed to migrate %s: %s", legacy_path.name, exc)

    if migrated:
        logger.info(
            "Migrated %d CIDR list file(s) from legacy path %s to %s",
            migrated,
            legacy_dir,
            target_dir,
        )
    return migrated
