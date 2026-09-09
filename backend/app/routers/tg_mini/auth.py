"""Authentication endpoints for Telegram Mini App."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

from .helpers import TelegramAuthRequest

router = APIRouter()


@router.post("/auth")
def tg_auth(payload: TelegramAuthRequest, request: Request, db: Session = Depends(get_db)):
    from app.routers import tg_mini as root

    token = root._get_bot_token(db)
    if not token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram bot не настроен")
    try:
        max_age_raw = root._get_setting(db, "telegram_auth_max_age_seconds")
        max_age = int(max_age_raw) if max_age_raw.isdigit() else 300
        tg_user = root._verify_telegram_init_data(payload.init_data, token, max_age=max_age)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    tg_id = str(tg_user.get("id", ""))
    user = db.query(User).filter(User.telegram_id == tg_id).first()
    if not user:
        root.admin_notify_service.send_tg_login_unlinked(
            db,
            telegram_id=tg_id,
            remote_addr=root.ip_restriction_service.get_client_ip(request),
            mini=True,
            client_timezone=root.get_client_timezone_from_request(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Этот Telegram аккаунт не привязан ни к одному пользователю панели",
        )
    access_token = root.create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "telegram_id": tg_id}
