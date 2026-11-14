"""Resolved filesystem paths for the backend package."""

from functools import lru_cache
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def resolve_backend_path(relative: str | Path) -> Path:
    return (BACKEND_ROOT / Path(relative)).resolve()


def resolve_sqlite_db_path(db_url: str, *, default_relative: str) -> Path:
    """Path of a ``sqlite:///`` database file; ``default_relative`` wins for other dialects."""
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", ""))
        if not db_path.is_absolute():
            db_path = BACKEND_ROOT / db_path
        return db_path.resolve()
    return (BACKEND_ROOT / default_relative).resolve()


@lru_cache
def get_cidr_list_dir() -> Path:
    from app.config import get_settings

    return resolve_backend_path(get_settings().cidr_list_dir)
