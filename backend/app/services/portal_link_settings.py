"""Portal link lifetime (AppSetting + .env sync)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services.env_file import EnvFileService

SETTING_KEY = "portal_link_ttl_days"
ENV_KEY = "PORTAL_LINK_TTL_DAYS"
DEFAULT_TTL_DAYS = 30
MAX_TTL_DAYS = 3650


def _env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def normalize_portal_link_ttl_days(value: object) -> int:
    """0 = unlimited; garbage/negative → default; too large → max."""
    try:
        days = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_TTL_DAYS
    if days < 0:
        return DEFAULT_TTL_DAYS
    return min(days, MAX_TTL_DAYS)


def get_portal_link_ttl_days(db: Session) -> int:
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if row is not None:
        return normalize_portal_link_ttl_days(row.value)
    env_raw = EnvFileService(_env_path()).get_env_value(ENV_KEY, str(DEFAULT_TTL_DAYS))
    return normalize_portal_link_ttl_days(env_raw)


def set_portal_link_ttl_days(db: Session, days: object) -> int:
    value = str(normalize_portal_link_ttl_days(days))
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=SETTING_KEY, value=value))
    EnvFileService(_env_path()).set_env_value(ENV_KEY, value)
    os.environ[ENV_KEY] = value
    db.commit()
    return int(value)


def portal_link_expires_at(created_at: datetime | None, ttl_days: int) -> datetime | None:
    """Naive UTC expiry; ``None`` when the link is unlimited or has no creation date."""
    if created_at is None or ttl_days <= 0:
        return None
    return created_at + timedelta(days=ttl_days)
