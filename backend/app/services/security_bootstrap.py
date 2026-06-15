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


def _validate_redis_rate_limit(settings: Settings) -> None:
    import os

    workers = max(1, int(os.environ.get("UVICORN_WORKERS", settings.uvicorn_workers or 1)))
    needs_redis = workers > 1 or settings.auth_rate_limit_backend == "redis" or settings.api_rate_limit_backend == "redis"
    if not needs_redis:
        return
    if not (settings.redis_url or "").strip():
        _fail(
            "Для UVICORN_WORKERS>1 или *_RATE_LIMIT_BACKEND=redis задайте REDIS_URL "
            "(см. SECURITY.md)."
        )
    if workers > 1 and settings.auth_rate_limit_backend != "redis":
        logger.warning(
            "UVICORN_WORKERS=%d, но AUTH_RATE_LIMIT_BACKEND=%s — используйте redis",
            workers,
            settings.auth_rate_limit_backend,
        )
    if workers > 1 and settings.api_rate_limit_backend != "redis":
        logger.warning(
            "UVICORN_WORKERS=%d, но API_RATE_LIMIT_BACKEND=%s — используйте redis",
            workers,
            settings.api_rate_limit_backend,
        )


def validate_panel_settings(settings: Settings) -> None:
    if settings.is_production:
        _validate_redis_rate_limit(settings)
    if not settings.is_production or not settings.require_production_secrets:
        return
    if settings.secret_key == _DEFAULT_SECRET_KEY or len(settings.secret_key) < 32:
        _fail(
            "В production задайте SECRET_KEY (минимум 32 случайных символа). "
            "Пример: openssl rand -hex 32"
        )
    bootstrap_password = (settings.default_admin_password or "").strip()
    if bootstrap_password and bootstrap_password.lower() in _WEAK_ADMIN_PASSWORDS:
        _fail(
            "В production нельзя использовать слабый DEFAULT_ADMIN_PASSWORD при установке. "
            "Задайте надёжный пароль в мастере установки; после входа он хранится только в БД."
        )


def validate_node_agent_key(api_key: str, *, production: bool) -> None:
    if not production:
        return
    if not api_key or api_key == _DEFAULT_NODE_AGENT_KEY or len(api_key) < 24:
        _fail(
            "В production задайте NODE_AGENT_API_KEY (минимум 24 случайных символа). "
            "Пример: openssl rand -hex 32"
        )
