"""Idempotent privacy upgrade steps (spec 12 Upgrade 1–5) run once at panel startup."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.app_setting_store import _get_setting, _set_setting
from app.services.config_access import migrate_grants_to_explicit_prefix
from app.services.qr_download import hash_pin, is_stored_pin_hash
from app.services.telegram_api import get_webhook_info_sync, set_webhook_sync

logger = logging.getLogger(__name__)

WEBHOOK_PRIVACY_UPGRADED = "telegram_webhook_privacy_upgraded"
NGINX_PRIVACY_APPLIED = "nginx_privacy_log_applied"
_WEBHOOK_PATH_MARKER = "/api/telegram/webhook/"

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def migrate_plain_qr_download_pin(db: Session) -> bool:
    """Hash plain-text global ``qr_download_pin`` once (B5). Returns True if migrated."""
    raw = (_get_setting(db, "qr_download_pin", "") or "").strip()
    if not raw or is_stored_pin_hash(raw):
        return False
    _set_setting(db, "qr_download_pin", hash_pin(raw))
    db.commit()
    logger.info("Migrated plain qr_download_pin to salted hash")
    return True


def _resolve_webhook_url(db: Session, secret: str) -> str | None:
    """Build webhook URL from DOMAIN / publish settings (no HTTP request at startup)."""
    from app.config import get_settings
    from app.services.env_file import EnvFileService
    from app.services.panel_publish_info import build_publish_access_url

    settings = get_settings()
    env = EnvFileService(_ENV_FILE)
    domain = (env.get_env_value("DOMAIN", "") or settings.domain or "").strip()
    if not domain:
        return None
    behind = settings.behind_nginx
    mode = (env.get_env_value("PUBLISH_MODE", "") or "").strip()
    if not mode:
        mode = "nginx_le" if behind else "http_direct"
    access_path = env.get_env_value("ACCESS_PATH", "") or settings.access_path or ""
    backend_port = env.get_env_value("BACKEND_PORT", "") or "8000"
    https_port = env.get_env_value("HTTPS_PUBLIC_PORT", "") or str(settings.https_public_port)
    root = build_publish_access_url(
        publish_mode=mode,
        domain=domain,
        backend_port=backend_port,
        https_public_port=https_port,
        behind_nginx=behind,
        access_path_value=access_path,
    )
    if not root:
        return None
    return f"{root.rstrip('/')}/api/telegram/webhook/{secret}"


def _ensure_webhook_secret(db: Session) -> str:
    import secrets

    secret = _get_setting(db, "telegram_webhook_secret")
    if not secret:
        secret = secrets.token_urlsafe(32)
        _set_setting(db, "telegram_webhook_secret", secret)
        db.commit()
    return secret


def _rewrite_webhook_url_secret(current_url: str, secret: str) -> str | None:
    """Keep host/path from the live Telegram webhook; only replace the path secret segment.

    Avoids pointing Telegram at a wrong DOMAIN-built URL (bot silence).
    """
    raw = (current_url or "").strip()
    idx = raw.find(_WEBHOOK_PATH_MARKER)
    if idx < 0:
        return None
    return f"{raw[: idx + len(_WEBHOOK_PATH_MARKER)]}{secret}"


def _webhook_url_for_upgrade(db: Session, bot_token: str, secret: str) -> str | None:
    """Prefer current getWebhookInfo URL; fall back to DOMAIN rebuild."""
    ok, info = get_webhook_info_sync(bot_token)
    if ok and isinstance(info, dict):
        current = str(info.get("url") or "").strip()
        if current:
            rewritten = _rewrite_webhook_url_secret(current, secret)
            if rewritten:
                return rewritten
            logger.warning(
                "Privacy upgrade: live webhook URL is not a panel webhook path; deferring re-register"
            )
            return None
    rebuilt = _resolve_webhook_url(db, secret)
    if rebuilt:
        logger.info("Privacy upgrade: no live webhook URL from Telegram; using DOMAIN rebuild")
    return rebuilt


def upgrade_telegram_webhook(db: Session) -> str:
    """Re-register webhook with secret + allowed_updates (A6–A7).

    Returns: ``skipped`` | ``ok`` | ``failed`` | ``deferred``.
    Sets ``telegram_webhook_secret_required`` only on successful setWebhook.
    Never rejects updates before that — failure leaves the bot accepting as today.
    """
    from app.services.telegram_transport import RELAY_NODES_SETTING

    if _get_setting(db, WEBHOOK_PRIVACY_UPGRADED, "") == "1":
        return "skipped"

    bot_token = (_get_setting(db, "telegram_bot_token") or "").strip()
    interactive = _get_setting(db, "telegram_bot_interactive_enabled", "false") == "true"
    webhook_set_at = (_get_setting(db, "telegram_webhook_set_at") or "").strip()
    relay = (_get_setting(db, RELAY_NODES_SETTING) or "").strip()

    # Not using panel webhook (polling / relay / bot off) — mark done, nothing to re-register.
    if not bot_token or not interactive or relay or not webhook_set_at:
        _set_setting(db, WEBHOOK_PRIVACY_UPGRADED, "1")
        db.commit()
        return "skipped"

    secret = _ensure_webhook_secret(db)
    url = _webhook_url_for_upgrade(db, bot_token, secret)
    if not url:
        logger.warning(
            "Privacy upgrade: cannot resolve webhook URL; "
            "retry on next start or when admin presses «Подключить»"
        )
        return "deferred"

    ok, error = set_webhook_sync(bot_token, url, secret_token=secret)
    if not ok:
        logger.warning(
            "Privacy upgrade: setWebhook failed (%s); keeping webhook without secret header requirement",
            error,
        )
        return "failed"

    _set_setting(db, "telegram_webhook_secret_required", "true")
    _set_setting(db, WEBHOOK_PRIVACY_UPGRADED, "1")
    db.commit()
    logger.info("Privacy upgrade: webhook re-registered with secret_token and allowed_updates")
    return "ok"


def warn_backup_groups_if_needed(db: Session) -> bool:
    """D1 upgrade: bell when group chat ids exist without backup password."""
    from app.services.backup_telegram_privacy import warn_if_group_recipients_without_password

    return warn_if_group_recipients_without_password(db)


def ensure_nginx_privacy_log() -> bool:
    """Install privacy access-log map + reload nginx with test/rollback (B6).

    Returns True when applied or already present; False on hard failure.
    Skips quietly when not behind nginx / DOMAIN unset / no sudo.
    """
    from app.config import get_settings
    from app.services.env_file import EnvFileService

    settings = get_settings()
    env = EnvFileService(_ENV_FILE)
    domain = (env.get_env_value("DOMAIN", "") or settings.domain or "").strip()
    behind = settings.behind_nginx or bool(domain)
    if not behind or not domain:
        return True  # nothing to do on direct-uvicorn installs

    common = _PROJECT_ROOT / "scripts" / "nginx-common.sh"
    if not common.is_file():
        logger.warning("Privacy upgrade: nginx-common.sh missing; skip privacy log")
        return False

    # Only ensure the conf.d snippet (map + log_format). Full vhost regen happens on
    # install/update / nginx-repair; here we must not break a running panel.
    script = f"""
set -euo pipefail
# shellcheck source=/dev/null
source "{common}"
nginx_common_init
nginx_ensure_privacy_log
if [[ "${{NGINX_PRIVACY_LOG_CHANGED:-false}}" != "true" ]]; then
  exit 0
fi
if ! nginx -t; then
  nginx_rollback_privacy_log
  exit 1
fi
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nginx; then
  systemctl reload nginx || nginx -s reload
else
  nginx -s reload || true
fi
rm -f "${{NGINX_PRIVACY_LOG_BAK:-}}"
"""
    run_env = os.environ.copy()
    run_env["DOMAIN"] = domain
    run_env["ENV_FILE"] = str(_PROJECT_ROOT / "backend" / ".env")
    try:
        result = subprocess.run(
            ["sudo", "-n", "bash", "-c", script],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env=run_env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Privacy upgrade: nginx privacy log ensure failed: %s", exc)
        return False

    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "unknown error").strip()
        logger.warning("Privacy upgrade: nginx privacy log ensure failed: %s", msg[:500])
        return False
    return True


def upgrade_nginx_privacy_log(db: Session) -> str:
    """Apply nginx privacy map once; marker only on success."""
    if _get_setting(db, NGINX_PRIVACY_APPLIED, "") == "1":
        return "skipped"
    if not ensure_nginx_privacy_log():
        return "failed"
    _set_setting(db, NGINX_PRIVACY_APPLIED, "1")
    db.commit()
    return "ok"


def run_privacy_upgrade(db: Session) -> dict[str, Any]:
    """Run Upgrade steps 1–5. Idempotent — second call is a no-op."""
    result: dict[str, Any] = {
        "grants_changed": 0,
        "pin_migrated": False,
        "webhook": "skipped",
        "backup_group_warned": False,
        "nginx": "skipped",
    }
    try:
        result["grants_changed"] = migrate_grants_to_explicit_prefix(db)
    except Exception:
        logger.exception("Privacy upgrade: grants migration failed")

    try:
        result["pin_migrated"] = migrate_plain_qr_download_pin(db)
    except Exception:
        logger.exception("Privacy upgrade: PIN migration failed")

    try:
        result["webhook"] = upgrade_telegram_webhook(db)
    except Exception:
        logger.exception("Privacy upgrade: webhook re-register failed")
        result["webhook"] = "failed"

    try:
        result["backup_group_warned"] = warn_backup_groups_if_needed(db)
    except Exception:
        logger.exception("Privacy upgrade: backup group warning failed")

    try:
        result["nginx"] = upgrade_nginx_privacy_log(db)
    except Exception:
        logger.exception("Privacy upgrade: nginx privacy log failed")
        result["nginx"] = "failed"

    return result
