"""Telegram bot webhook endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.routers.maintenance import _get_setting, _telegram_settings_response
from app.schemas import TelegramBotInfoResponse, TelegramLinkCodeResponse
from app.services.feature_guards import get_feature_service
from app.services.rate_limit.sliding_window import RateLimitExceeded
from app.services.telegram_bot import telegram_bot_service
from app.services.telegram_link import create_link_code
from app.services.telegram_webhook_security import (
    consume_webhook_rate_limit,
    get_telegram_webhook_client_ip,
    is_telegram_ip,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram-bot"])


def _ensure_telegram_module() -> None:
    if not get_feature_service().is_enabled("telegram"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Модуль Telegram отключён")


def _bot_info(db: Session) -> TelegramBotInfoResponse:
    username = (_get_setting(db, "telegram_bot_username") or "").strip().lstrip("@")
    return TelegramBotInfoResponse(
        bot_username=username,
        bot_url=f"https://t.me/{username}" if username else "",
    )


@router.post("/webhook/{secret}")
async def telegram_webhook(
    secret: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _ensure_telegram_module()

    if _get_setting(db, "telegram_bot_interactive_enabled", "false") != "true":
        return {"ok": True}

    expected = _get_setting(db, "telegram_webhook_secret")
    if not expected or secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    client_ip = get_telegram_webhook_client_ip(request)
    if not is_telegram_ip(client_ip):
        logger.warning("Telegram webhook rejected IP=%s", client_ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        consume_webhook_rate_limit(client_ip)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail, headers=exc.headers) from exc

    try:
        update = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc

    settings = _telegram_settings_response(db, request)
    await telegram_bot_service.handle_update(db, update, mini_app_url=settings.mini_app_url)
    return {"ok": True}


@router.get("/bot-info", response_model=TelegramBotInfoResponse)
def telegram_bot_info(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Bot username/URL for any logged-in user (e.g. self-link UI)."""
    _ensure_telegram_module()
    return _bot_info(db)


@router.get("/link-code", response_model=TelegramLinkCodeResponse)
def telegram_link_code(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not get_feature_service().is_enabled("telegram"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Модуль Telegram отключён")
    if not _get_setting(db, "telegram_bot_token"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен бота не настроен")
    code, ttl = create_link_code(db, current_user)
    return TelegramLinkCodeResponse(code=code, expires_in_seconds=ttl)
