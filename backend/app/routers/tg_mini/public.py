"""Public Mini App settings: what the login/error screen needs before auth."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.app_setting_store import _get_setting

router = APIRouter()


@router.get("/config")
def mini_public_config(db: Session = Depends(get_db)):
    """Bot link for the "open in Telegram" hint. No token, no auth."""
    token = _get_setting(db, "telegram_bot_token")
    username = (_get_setting(db, "telegram_bot_username") or "").strip().lstrip("@")
    return {"bot_username": username or None, "bot_configured": bool(token)}
