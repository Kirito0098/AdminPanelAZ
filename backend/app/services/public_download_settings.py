"""Public route-file download toggle (AppSetting + .env sync)."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services.env_file import EnvFileService

SETTING_KEY = "public_download_enabled"
ENV_KEY = "PUBLIC_DOWNLOAD_ENABLED"


def _env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def is_public_download_enabled(db: Session) -> bool:
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if row is not None:
        return row.value.strip().lower() in {"1", "true", "yes", "on"}
    env_raw = EnvFileService(_env_path()).get_env_value(ENV_KEY, "false")
    return env_raw.strip().lower() in {"1", "true", "yes", "on"}


def set_public_download_enabled(db: Session, enabled: bool) -> bool:
    value = "true" if enabled else "false"
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=SETTING_KEY, value=value))
    EnvFileService(_env_path()).set_env_value(ENV_KEY, value)
    os.environ[ENV_KEY] = value
    db.commit()
    return enabled
