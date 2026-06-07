"""Password strength validation for admin panel accounts."""

from __future__ import annotations

import re

from fastapi import HTTPException, status

from app.config import Settings, get_settings

_WEAK_PASSWORDS = frozenset({"admin", "password", "123456", "12345678", "qwerty", "changeme"})


def effective_min_password_length(settings: Settings | None = None) -> int:
    cfg = settings or get_settings()
    if cfg.is_production or cfg.enforce_password_policy:
        return max(4, cfg.min_password_length)
    return 4


def validate_password(password: str, *, username: str | None = None, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    min_len = effective_min_password_length(cfg)
    if len(password) < min_len:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Пароль должен содержать не менее {min_len} символов",
        )
    if not (cfg.is_production or cfg.enforce_password_policy):
        return
    lowered = password.lower()
    if lowered in _WEAK_PASSWORDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Слишком простой пароль")
    if username and lowered == username.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пароль не должен совпадать с именем пользователя",
        )
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пароль должен содержать буквы и цифры",
        )
