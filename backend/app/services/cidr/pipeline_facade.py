"""Patchable facade for CIDR pipeline modules (test hooks)."""

from app.services.cidr.pipeline import constants
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService
from app.services.cidr.pipeline.download import _download_text

__all__ = [
    "CidrDbUpdaterService",
    "_download_text",
    "ENV_FILE_PATH",
    "LIST_DIR",
    "BASELINE_DIR",
    "RUNTIME_BACKUP_ROOT",
]

ENV_FILE_PATH = constants.ENV_FILE_PATH
LIST_DIR = constants.LIST_DIR
BASELINE_DIR = constants.BASELINE_DIR
RUNTIME_BACKUP_ROOT = constants.RUNTIME_BACKUP_ROOT
