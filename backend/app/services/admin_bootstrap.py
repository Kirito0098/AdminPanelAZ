"""Bootstrap admin credentials: .env is used only until the password is stored in SQLite."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.config import Settings, get_settings
from app.models import User, UserRole
from app.services.env_file import EnvFileService

logger = logging.getLogger(__name__)

_ENV_ADMIN_PASSWORD_KEY = "DEFAULT_ADMIN_PASSWORD"
_ENV_ADMIN_USERNAME_KEY = "DEFAULT_ADMIN_USERNAME"
_ENV_ADMIN_MUST_CHANGE_KEY = "DEFAULT_ADMIN_MUST_CHANGE_PASSWORD"


def resolve_backend_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def scrub_admin_bootstrap_secret_from_env(
    *,
    env_path: Path | None = None,
    settings: Settings | None = None,
) -> bool:
    """Remove plaintext bootstrap password from .env once it lives in the database."""
    cfg = settings or get_settings()
    path = env_path or resolve_backend_env_path()
    svc = EnvFileService(path)
    current = svc.get_env_value(_ENV_ADMIN_PASSWORD_KEY, "__missing__")
    if current in ("__missing__", ""):
        return False
    svc.set_env_value(_ENV_ADMIN_PASSWORD_KEY, "")
    logger.info(
        "Cleared %s in %s — admin password is stored in the database only",
        _ENV_ADMIN_PASSWORD_KEY,
        path,
    )
    return True


def should_scrub_env_after_password_change(username: str, settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return username == cfg.default_admin_username


def upsert_bootstrap_admin(
    db: Session,
    *,
    force: bool = False,
    settings: Settings | None = None,
) -> str:
    """
    Create the default admin from DEFAULT_ADMIN_* or update it when force=True (install wizard).

    Returns: "created", "updated", or "skipped".
    """
    cfg = settings or get_settings()
    username = cfg.default_admin_username
    if not username:
        raise ValueError("DEFAULT_ADMIN_USERNAME is empty")

    password = (cfg.default_admin_password or "").strip()
    user = db.query(User).filter(User.username == username).first()

    if user and not force:
        return "skipped"

    if not password:
        if user:
            return "skipped"
        raise ValueError(
            f"{_ENV_ADMIN_PASSWORD_KEY} is empty and admin {username!r} does not exist in the database"
        )

    if user:
        user.password_hash = get_password_hash(password)
        user.must_change_password = cfg.default_admin_must_change_password
        user.is_active = True
        if user.role != UserRole.admin:
            user.role = UserRole.admin
        db.commit()
        return "updated"

    db.add(
        User(
            username=username,
            password_hash=get_password_hash(password),
            role=UserRole.admin,
            theme="dark",
            must_change_password=cfg.default_admin_must_change_password,
            is_active=True,
        )
    )
    db.commit()
    return "created"
