import hashlib
import hmac
import os
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import authenticate_user, create_access_token, get_current_user, get_password_hash, verify_password
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User, UserRole
from app.schemas import LoginRequest, MessageResponse, PasswordChangeRequest, Token, UserResponse
from app.services.captcha import captcha_service
from app.services.ip_restriction import ip_restriction_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _get_telegram_auth_settings(db: Session) -> tuple[str, str, int]:
    token_row = db.query(AppSetting).filter(AppSetting.key == "telegram_bot_token").first()
    username_row = db.query(AppSetting).filter(AppSetting.key == "telegram_bot_username").first()
    max_age_row = db.query(AppSetting).filter(AppSetting.key == "telegram_auth_max_age_seconds").first()
    token = token_row.value if token_row else os.getenv("TELEGRAM_AUTH_BOT_TOKEN", "")
    username = username_row.value if username_row else os.getenv("TELEGRAM_AUTH_BOT_USERNAME", "")
    max_age = int(max_age_row.value) if max_age_row and max_age_row.value.isdigit() else 300
    return token.strip(), username.strip(), max(30, min(max_age, 86400))


def _verify_telegram_login(payload: dict[str, str], bot_token: str, max_age: int) -> tuple[bool, str]:
    received_hash = (payload.get("hash") or "").strip().lower()
    auth_date_raw = (payload.get("auth_date") or "").strip()
    telegram_id = (payload.get("id") or "").strip()
    if not received_hash or not auth_date_raw or not telegram_id:
        return False, "Некорректные данные Telegram авторизации"
    if not auth_date_raw.isdigit():
        return False, "Некорректная дата Telegram авторизации"
    auth_date = int(auth_date_raw)
    if abs(int(time.time()) - auth_date) > max_age:
        return False, "Время Telegram авторизации истекло"
    data_parts = [f"{k}={payload[k]}" for k in sorted(payload.keys()) if k != "hash" and payload.get(k) is not None]
    data_check_string = "\n".join(data_parts)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        return False, "Проверка подписи Telegram не пройдена"
    return True, ""


def _issue_token(user: User) -> Token:
    token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return Token(access_token=token)


def _login_with_checks(
    db: Session,
    request: Request,
    username: str,
    password: str,
    captcha_id: str | None = None,
    captcha_text: str | None = None,
) -> Token:
    client_ip = ip_restriction_service.get_client_ip(request)
    if ip_restriction_service.login_needs_captcha(client_ip):
        if not captcha_id or not captcha_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Требуется капча")
        if not captcha_service.verify(captcha_id, captcha_text):
            ip_restriction_service.record_login_attempt(client_ip, success=False)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный код капчи")
    user = authenticate_user(db, username, password)
    if not user:
        attempts = ip_restriction_service.record_login_attempt(client_ip, success=False)
        detail = "Неверный логин или пароль"
        if attempts > 2:
            detail += " (требуется капча)"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
    ip_restriction_service.record_login_attempt(client_ip, success=True)
    return _issue_token(user)


@router.get("/captcha")
def get_captcha():
    captcha_id, image_bytes = captcha_service.create_captcha()
    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"X-Captcha-Id": captcha_id, "Cache-Control": "no-store"},
    )


@router.get("/captcha/required")
def captcha_required(request: Request):
    client_ip = ip_restriction_service.get_client_ip(request)
    return {"required": ip_restriction_service.login_needs_captcha(client_ip)}


@router.get("/telegram/config")
def telegram_login_config(db: Session = Depends(get_db)):
    token, username, max_age = _get_telegram_auth_settings(db)
    return {
        "enabled": bool(token and username),
        "bot_username": username,
        "max_age_seconds": max_age,
    }


@router.get("/telegram")
def telegram_login_callback(request: Request, db: Session = Depends(get_db)):
    token, _, max_age = _get_telegram_auth_settings(db)
    if not token:
        raise HTTPException(status_code=503, detail="Telegram авторизация не настроена")
    payload = dict(request.query_params)
    ok, err = _verify_telegram_login(payload, token, max_age)
    if not ok:
        raise HTTPException(status_code=401, detail=err)
    tg_id = str(payload.get("id", ""))
    user = db.query(User).filter(User.username == f"tg_{tg_id}").first()
    if not user:
        user = User(
            username=f"tg_{tg_id}",
            password_hash=get_password_hash(tg_id),
            role=UserRole.user,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    access = _issue_token(user)
    redirect_url = f"/login?token={access.access_token}"
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    return _login_with_checks(db, request, form_data.username, form_data.password)


@router.post("/login/json", response_model=Token)
def login_json(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return _login_with_checks(
        db,
        request,
        payload.username,
        payload.password,
        payload.captcha_id,
        payload.captcha_text,
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный текущий пароль")
    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    db.commit()
    return MessageResponse(message="Пароль успешно изменён")
