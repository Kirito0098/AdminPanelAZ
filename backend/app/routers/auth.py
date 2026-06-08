import hashlib
import hmac
import json
import os
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user,
    create_2fa_pending_token,
    create_access_token,
    decode_2fa_pending_token,
    get_current_user,
    get_password_hash,
    require_admin,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.models import AppSetting, User, UserRole
from app.schemas import (
    Login2FARequest,
    Login2FARequired,
    LoginRequest,
    MessageResponse,
    PasswordChangeRequest,
    Token,
    TwoFABackupCodesResponse,
    TwoFADisableRequest,
    TwoFAEnableRequest,
    TwoFASetupResponse,
    TwoFAStatusResponse,
    UserResponse,
)
from app.services.action_log import log_action
from app.services.auth_rate_limit import auth_rate_limit_service
from app.services.captcha import captcha_service
from app.services.ip_restriction import ip_restriction_service
from app.services.password_policy import validate_password
from app.services.refresh_token import (
    create_refresh_token,
    revoke_all_user_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.services.admin_notify import admin_notify_service
from app.services.notify_time import get_client_timezone_from_request
from app.services.totp_service import (
    encrypt_backup_codes,
    encrypt_totp_secret,
    generate_backup_codes,
    generate_qr_data_url,
    generate_totp_secret,
    get_totp_uri,
    require_valid_totp,
    verify_totp_code,
)

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


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    secure = settings.refresh_token_cookie_secure or settings.is_production or settings.enforce_https
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=raw_token,
        httponly=True,
        secure=secure,
        samesite=settings.refresh_token_cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.refresh_token_cookie_name, path="/api/auth")


def _issue_token_pair(user: User, db: Session, response: Response | None = None) -> Token:
    access = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    raw_refresh, _ = create_refresh_token(db, user)
    if response is not None:
        _set_refresh_cookie(response, raw_refresh)
    return Token(access_token=access)


def _login_with_checks(
    db: Session,
    request: Request,
    username: str,
    password: str,
    captcha_id: str | None = None,
    captcha_text: str | None = None,
    response: Response | None = None,
) -> Token | Login2FARequired:
    client_ip = ip_restriction_service.get_client_ip(request)
    auth_rate_limit_service.check(client_ip)
    if ip_restriction_service.login_needs_captcha(client_ip):
        if not captcha_id or not captcha_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Требуется капча")
        if not captcha_service.verify(captcha_id, captcha_text):
            ip_restriction_service.record_login_attempt(client_ip, success=False)
            auth_rate_limit_service.record_failure(client_ip)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный код капчи")
    user = authenticate_user(db, username, password)
    if not user:
        attempts = ip_restriction_service.record_login_attempt(client_ip, success=False)
        auth_rate_limit_service.record_failure(client_ip)
        if settings.audit_log_enabled:
            log_action(
                db,
                action="login_failed",
                username=username,
                remote_addr=client_ip,
                details="invalid credentials",
            )
        admin_notify_service.send_login_failed(
            db,
            actor_username=username,
            remote_addr=client_ip,
            client_timezone=get_client_timezone_from_request(request),
        )
        detail = "Неверный логин или пароль"
        if attempts > 2:
            detail += " (требуется капча)"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    if user.totp_enabled and user.role == UserRole.admin:
        return Login2FARequired(temp_token=create_2fa_pending_token(user.username))

    ip_restriction_service.record_login_attempt(client_ip, success=True)
    auth_rate_limit_service.record_success(client_ip)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="login_success",
            user_id=user.id,
            username=user.username,
            remote_addr=client_ip,
        )
    if user.role != UserRole.viewer:
        admin_notify_service.send_login_success(
            db,
            actor_username=user.username,
            remote_addr=client_ip,
            client_timezone=get_client_timezone_from_request(request),
        )
    return _issue_token_pair(user, db, response)


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
            telegram_id=tg_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.telegram_id:
        user.telegram_id = tg_id
        db.commit()
    client_ip = ip_restriction_service.get_client_ip(request)
    if user.role != UserRole.viewer:
        admin_notify_service.send_login_success(
            db,
            actor_username=user.username,
            remote_addr=client_ip,
            client_timezone=get_client_timezone_from_request(request),
        )
    access = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    redirect_url = f"/login#token={access.access_token}"
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/login", response_model=Token)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    result = _login_with_checks(db, request, form_data.username, form_data.password, response=response)
    if isinstance(result, Login2FARequired):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуется код 2FA")
    return result


@router.post("/login/json", response_model=Token | Login2FARequired)
def login_json(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    return _login_with_checks(
        db,
        request,
        payload.username,
        payload.password,
        payload.captcha_id,
        payload.captcha_text,
        response=response,
    )


@router.post("/login/2fa", response_model=Token)
def login_2fa(payload: Login2FARequest, request: Request, response: Response, db: Session = Depends(get_db)):
    client_ip = ip_restriction_service.get_client_ip(request)
    auth_rate_limit_service.check(client_ip)
    username = decode_2fa_pending_token(payload.temp_token)
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or not user.totp_enabled:
        auth_rate_limit_service.record_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код 2FA")
    if not verify_totp_code(user, payload.code):
        auth_rate_limit_service.record_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код 2FA")
    ip_restriction_service.record_login_attempt(client_ip, success=True)
    auth_rate_limit_service.record_success(client_ip)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="login_success",
            user_id=user.id,
            username=user.username,
            remote_addr=client_ip,
            details="2fa",
        )
    if user.role != UserRole.viewer:
        admin_notify_service.send_login_success(
            db,
            actor_username=user.username,
            remote_addr=client_ip,
            client_timezone=get_client_timezone_from_request(request),
        )
    db.commit()
    return _issue_token_pair(user, db, response)


@router.post("/refresh", response_model=Token)
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(settings.refresh_token_cookie_name)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh-токен отсутствует")
    new_raw, user = rotate_refresh_token(db, raw)
    access = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    _set_refresh_cookie(response, new_raw)
    return Token(access_token=access)


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(settings.refresh_token_cookie_name)
    if raw:
        revoke_refresh_token(db, raw)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Выход выполнен")


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный текущий пароль")
    validate_password(payload.new_password, username=current_user.username)
    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    revoke_all_user_tokens(db, current_user.id)
    db.commit()
    if settings.audit_log_enabled:
        log_action(
            db,
            action="password_change",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
        )
    return MessageResponse(message="Пароль успешно изменён")


@router.get("/2fa/status", response_model=TwoFAStatusResponse)
def twofa_status(current_user: User = Depends(require_admin)):
    remaining = 0
    if current_user.totp_backup_codes_encrypted:
        try:
            from app.services.crypto import decrypt_secret

            codes = json.loads(decrypt_secret(current_user.totp_backup_codes_encrypted, settings.secret_key))
            remaining = len(codes)
        except Exception:
            remaining = 0
    return TwoFAStatusResponse(enabled=current_user.totp_enabled, backup_codes_remaining=remaining)


@router.post("/2fa/setup", response_model=TwoFASetupResponse)
def twofa_setup(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if current_user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA уже включена")
    secret = generate_totp_secret()
    current_user.totp_secret_encrypted = encrypt_totp_secret(secret)
    db.commit()
    uri = get_totp_uri(current_user, secret)
    return TwoFASetupResponse(secret=secret, otpauth_uri=uri, qr_data_url=generate_qr_data_url(uri))


@router.post("/2fa/enable", response_model=TwoFABackupCodesResponse)
def twofa_enable(
    payload: TwoFAEnableRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if current_user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA уже включена")
    if not current_user.totp_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сначала выполните /2fa/setup")
    require_valid_totp(current_user, payload.code)
    backup_codes = generate_backup_codes()
    current_user.totp_enabled = True
    current_user.totp_backup_codes_encrypted = encrypt_backup_codes(backup_codes)
    db.commit()
    if settings.audit_log_enabled:
        log_action(
            db,
            action="2fa_enable",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
        )
    return TwoFABackupCodesResponse(backup_codes=backup_codes)


@router.post("/2fa/disable", response_model=MessageResponse)
def twofa_disable(
    payload: TwoFADisableRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not current_user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA не включена")
    require_valid_totp(current_user, payload.code)
    current_user.totp_enabled = False
    current_user.totp_secret_encrypted = None
    current_user.totp_backup_codes_encrypted = None
    db.commit()
    if settings.audit_log_enabled:
        log_action(
            db,
            action="2fa_disable",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
        )
    return MessageResponse(message="2FA отключена")


@router.post("/2fa/regenerate-backup-codes", response_model=TwoFABackupCodesResponse)
def twofa_regenerate_backup(
    payload: TwoFADisableRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not current_user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA не включена")
    require_valid_totp(current_user, payload.code)
    backup_codes = generate_backup_codes()
    current_user.totp_backup_codes_encrypted = encrypt_backup_codes(backup_codes)
    db.commit()
    return TwoFABackupCodesResponse(backup_codes=backup_codes)
