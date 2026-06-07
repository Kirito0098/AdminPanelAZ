"""Startup validation for production deployments."""

from __future__ import annotations

import logging
import sys

from app.config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_SECRET_KEY = "change-me-in-production-use-long-random-string"
_DEFAULT_NODE_AGENT_KEY = "change-me-node-agent-key"
_WEAK_ADMIN_PASSWORDS = frozenset({"admin", "password", "123456"})


def _fail(message: str) -> None:
    logger.critical(message)
    print(f"SECURITY: {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_panel_settings(settings: Settings) -> None:
    if not settings.is_production or not settings.require_production_secrets:
        return
    if settings.secret_key == _DEFAULT_SECRET_KEY or len(settings.secret_key) < 32:
        _fail(
            "В production задайте SECRET_KEY (минимум 32 случайных символа). "
            "Пример: openssl rand -hex 32"
        )
    if settings.default_admin_password.lower() in _WEAK_ADMIN_PASSWORDS:
        _fail(
            "В production нельзя использовать слабый DEFAULT_ADMIN_PASSWORD. "
            "Задайте надёжный пароль в .env до первого запуска."
        )


def validate_node_agent_key(api_key: str, *, production: bool) -> None:
    if not production:
        return
    if not api_key or api_key == _DEFAULT_NODE_AGENT_KEY or len(api_key) < 24:
        _fail(
            "В production задайте NODE_AGENT_API_KEY (минимум 24 случайных символа). "
            "Пример: openssl rand -hex 32"
        )
