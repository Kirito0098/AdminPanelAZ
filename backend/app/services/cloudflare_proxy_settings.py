"""Cloudflare proxy settings helpers and refresh orchestration."""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting
from app.services.cloudflare_realip import (
    fetch_cloudflare_proxy_snippets,
    is_valid_origin_allow_conf,
)
from app.services.env_file import EnvFileService

ENV_CLOUDFLARE_PROXY_ENABLED = "CLOUDFLARE_PROXY_ENABLED"
ENV_CLOUDFLARE_ORIGIN_LOCK = "CLOUDFLARE_ORIGIN_LOCK"
ENV_CLOUDFLARE_IPS_AUTO_UPDATE = "CLOUDFLARE_IPS_AUTO_UPDATE"
ENV_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS = "CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS"

SETTING_CLOUDFLARE_PROXY_ENABLED = "cloudflare_proxy_enabled"
SETTING_CLOUDFLARE_ORIGIN_LOCK = "cloudflare_origin_lock"
SETTING_CLOUDFLARE_IPS_AUTO_UPDATE = "cloudflare_ips_auto_update"
SETTING_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS = "cloudflare_ips_update_interval_days"

SETTING_LAST_SUCCESS_AT = "cloudflare_ips_last_success_at"
SETTING_LAST_HASH = "cloudflare_ips_last_hash"
SETTING_LAST_ERROR = "cloudflare_ips_last_error"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_APPLY_SCRIPT = _PROJECT_ROOT / "scripts" / "nginx-cloudflare-realip-apply.sh"
_REPAIR_SCRIPT = _PROJECT_ROOT / "scripts" / "nginx-repair.sh"


def _env_default_enabled() -> bool:
    return bool(get_settings().cloudflare_proxy_enabled)


def _env_default_origin_lock() -> bool:
    return bool(get_settings().cloudflare_origin_lock)


def _env_default_auto_update() -> bool:
    return bool(get_settings().cloudflare_ips_auto_update)


def _env_default_interval_days() -> int:
    return int(get_settings().cloudflare_ips_update_interval_days)


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _as_bool(value: str, default: bool) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    return raw in _TRUE_VALUES


def _as_int(value: str, default: int) -> int:
    raw = (value or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _env_service() -> EnvFileService:
    return EnvFileService(_ENV_FILE)


def origin_allow_snippet_path() -> Path:
    base = Path(os.environ.get("NGINX_SNIPPETS_DIR", "/etc/nginx/snippets"))
    return base / "cloudflare-origin-allow.conf"


def has_valid_origin_allow_snippet() -> bool:
    path = origin_allow_snippet_path()
    if not path.is_file():
        return False
    try:
        return is_valid_origin_allow_conf(path.read_text(encoding="utf-8"))
    except OSError:
        return False


def get_cloudflare_proxy_state(db: Session) -> dict:
    settings = get_settings()
    return {
        "enabled": _as_bool(
            _get_setting(db, SETTING_CLOUDFLARE_PROXY_ENABLED, ""),
            settings.cloudflare_proxy_enabled,
        ),
        "origin_lock_enabled": _as_bool(
            _get_setting(db, SETTING_CLOUDFLARE_ORIGIN_LOCK, ""),
            settings.cloudflare_origin_lock,
        ),
        "auto_update": _as_bool(
            _get_setting(db, SETTING_CLOUDFLARE_IPS_AUTO_UPDATE, ""),
            settings.cloudflare_ips_auto_update,
        ),
        "interval_days": _as_int(
            _get_setting(db, SETTING_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS, ""),
            settings.cloudflare_ips_update_interval_days,
        ),
        "last_success_at": _get_setting(db, SETTING_LAST_SUCCESS_AT, "") or None,
        "last_hash": _get_setting(db, SETTING_LAST_HASH, "") or None,
        "last_error": _get_setting(db, SETTING_LAST_ERROR, "") or None,
    }


def set_cloudflare_proxy_flags(
    db: Session,
    *,
    enabled: bool | None = None,
    origin_lock_enabled: bool | None = None,
    auto_update: bool | None = None,
    interval_days: int | None = None,
) -> dict:
    env = _env_service()
    current_state = get_cloudflare_proxy_state(db)
    resulting_enabled = current_state["enabled"] if enabled is None else enabled

    if origin_lock_enabled is True and not resulting_enabled:
        raise ValueError("CLOUDFLARE_ORIGIN_LOCK cannot be enabled when proxy is disabled")

    if enabled is not None:
        value = "true" if enabled else "false"
        _set_setting(db, SETTING_CLOUDFLARE_PROXY_ENABLED, value)
        env.set_env_value(ENV_CLOUDFLARE_PROXY_ENABLED, value)
        os.environ[ENV_CLOUDFLARE_PROXY_ENABLED] = value
        if enabled is False and origin_lock_enabled is None:
            origin_lock_enabled = False

    if origin_lock_enabled is not None:
        value = "true" if origin_lock_enabled else "false"
        _set_setting(db, SETTING_CLOUDFLARE_ORIGIN_LOCK, value)
        env.set_env_value(ENV_CLOUDFLARE_ORIGIN_LOCK, value)
        os.environ[ENV_CLOUDFLARE_ORIGIN_LOCK] = value

    if auto_update is not None:
        value = "true" if auto_update else "false"
        _set_setting(db, SETTING_CLOUDFLARE_IPS_AUTO_UPDATE, value)
        env.set_env_value(ENV_CLOUDFLARE_IPS_AUTO_UPDATE, value)
        os.environ[ENV_CLOUDFLARE_IPS_AUTO_UPDATE] = value

    if interval_days is not None:
        value = str(int(interval_days))
        _set_setting(db, SETTING_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS, value)
        env.set_env_value(ENV_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS, value)
        os.environ[ENV_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS] = value

    db.commit()
    return get_cloudflare_proxy_state(db)

def _run_apply_script(realip_file: Path, allow_file: Path) -> tuple[str, str]:
    run_env = os.environ.copy()
    result = subprocess.run(
        ["sudo", "-n", "bash", str(_APPLY_SCRIPT), str(realip_file), str(allow_file)],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        env=run_env,
    )
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        message = stderr or stdout or "unknown error"
        raise RuntimeError(
            f"Не удалось применить списки IP Cloudflare (код выхода {result.returncode}): {message}"
        )
    return stdout, stderr


def _mark_success(db: Session, *, content_hash: str) -> None:
    _set_setting(db, SETTING_LAST_SUCCESS_AT, _now_iso())
    _set_setting(db, SETTING_LAST_HASH, content_hash)
    _set_setting(db, SETTING_LAST_ERROR, "")
    db.commit()


def _mark_failure(db: Session, error: str) -> None:
    _set_setting(db, SETTING_LAST_ERROR, error)
    db.commit()


def refresh_cloudflare_ips(db: Session, *, force: bool = False) -> dict:
    try:
        realip_body, allow_body, content_hash = fetch_cloudflare_proxy_snippets()
        state = get_cloudflare_proxy_state(db)
        if not force and state.get("last_hash") == content_hash:
            _mark_success(db, content_hash=content_hash)
            return {
                "success": True,
                "applied": False,
                "forced": force,
                "changed": False,
                "hash": content_hash,
                "message": "Списки IP Cloudflare не изменились; применение пропущено.",
                "state": get_cloudflare_proxy_state(db),
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            realip_file = Path(tmpdir) / "cloudflare-realip.conf"
            allow_file = Path(tmpdir) / "cloudflare-origin-allow.conf"
            realip_file.write_text(realip_body, encoding="utf-8")
            allow_file.write_text(allow_body, encoding="utf-8")
            stdout, stderr = _run_apply_script(realip_file, allow_file)

        _mark_success(db, content_hash=content_hash)
        message = "Списки IP Cloudflare успешно обновлены."
        if stdout:
            message = f"{message} {stdout}".strip()
        if stderr:
            message = f"{message} {stderr}".strip()
        return {
            "success": True,
            "applied": True,
            "forced": force,
            "changed": True,
            "hash": content_hash,
            "message": message,
            "state": get_cloudflare_proxy_state(db),
        }
    except Exception as exc:
        error = str(exc)
        _mark_failure(db, error)
        return {
            "success": False,
            "applied": False,
            "forced": force,
            "changed": False,
            "error": error,
            "state": get_cloudflare_proxy_state(db),
        }


def regenerate_panel_nginx_for_cloudflare_proxy() -> tuple[str, str]:
    domain = _env_service().get_env_value("DOMAIN", "").strip()
    if not domain:
        raise RuntimeError("Для перегенерации nginx требуется переменная DOMAIN")
    if not _REPAIR_SCRIPT.is_file():
        raise RuntimeError(f"Скрипт перегенерации nginx панели не найден: {_REPAIR_SCRIPT}")

    run_env = os.environ.copy()
    run_env["DOMAIN"] = domain
    run_env["ENV_FILE"] = str(_ENV_FILE)
    # Nginx reload is enough: flags already persisted to DB/.env. Restarting the
    # panel service here caused a transient UI 502 on every proxy-mode toggle.
    result = subprocess.run(
        [
            "sudo",
            "-n",
            "bash",
            str(_REPAIR_SCRIPT),
            "--non-interactive",
            "--no-panel-restart",
        ],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        env=run_env,
    )
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        message = stderr or stdout or "unknown error"
        raise RuntimeError(
            f"Не удалось перегенерировать nginx для Cloudflare (код выхода {result.returncode}): {message}"
        )
    return stdout, stderr
