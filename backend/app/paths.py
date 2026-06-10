"""Resolved filesystem paths for the backend package."""

from functools import lru_cache
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def resolve_backend_path(relative: str | Path) -> Path:
    return (BACKEND_ROOT / Path(relative)).resolve()


@lru_cache
def get_cidr_list_dir() -> Path:
    from app.config import get_settings

    return resolve_backend_path(get_settings().cidr_list_dir)
