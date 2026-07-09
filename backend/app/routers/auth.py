import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import timedelta
from urllib.parse import quote

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
    PasskeyAuthOptionsRequest,
    PasskeyAuthVerifyRequest,
    PasskeyCredentialResponse,
    PasskeyListResponse,
    PasskeyRegisterOptionsResponse,
    PasskeyRegisterVerifyRequest,
    PasskeyRenameRequest,
    PasswordChangeRequest,
    TelegramOidcTokenRequest,
    Token,
    TwoFABackupCodesResponse,
    TwoFADisableRequest,
    TwoFAEnableRequest,
    TwoFASetupResponse,
    TwoFAStatusResponse,
    UserResponse,
)
from app.services.action_log import log_action
from app.services.admin_bootstrap import (
    scrub_admin_bootstrap_secret_from_env,
    should_scrub_env_after_password_change,
)
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
from app.services.active_web_session import active_web_session_service
from app.services.admin_notify import admin_notify_service
from app.services.user_agent_format import user_agent_from_request
from app.services.notify_time import get_client_timezone_from_request
from app.services.panel_paths import auth_cookie_path, with_access_path
from app.services.panel_publish_info import resolve_request_url_root
from app.services.telegram_oidc import (
    build_authorization_url,
    exchange_authorization_code,
    pkce_verifier,
    pop_oidc_state,
    telegram_id_from_claims,
    verify_id_token,
)
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
from app.services.webauthn_service import list_passkeys, user_has_passkeys, webauthn_service

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


def _get_telegram_oidc_settings(db: Session) -> tuple[bool, str, str]:
    enabled_row = db.query(AppSetting).filter(AppSetting.key == "telegram_oidc_enabled").first()
    client_id_row = db.query(AppSetting).filter(AppSetting.key == "telegram_oidc_client_id").first()
    secret_row = db.query(AppSetting).filter(AppSetting.key == "telegram_oidc_client_secret").first()
    enabled = (enabled_row.value if enabled_row else os.getenv("TELEGRAM_OIDC_ENABLED", "")).lower() == "true"
    client_id = (client_id_row.value if client_id_row else os.getenv("TELEGRAM_OIDC_CLIENT_ID", "")).strip()
    client_secret = (secret_row.value if secret_row else os.getenv("TELEGRAM_OIDC_CLIENT_SECRET", "")).strip()
    return enabled, client_id, client_secret


def _telegram_oidc_callback_url(request: Request) -> str:
    root = resolve_request_url_root(request, behind_nginx=settings.behind_nginx).rstrip("/")
    return f"{root}/api/auth/telegram/oidc/callback"


def _legacy_login_enabled(db: Session) -> bool:
    oidc_row = db.query(AppSetting).filter(AppSetting.key == "telegram_oidc_enabled").first()
    if oidc_row and oidc_row.value == "true":
        return False
    row = db.query(AppSetting).filter(AppSetting.key == "telegram_legacy_login_enabled").first()
    if row is None:
        return True
    return row.value != "false"


def _resolve_user_by_telegram_id(db: Session, tg_id: str) -> User | None:
    user = db.query(User).filter(User.telegram_id == tg_id).first()
    if user:
        return user
    user = db.query(User).filter(User.username == f"tg_{tg_id}").first()
    if user and not user.telegram_id:
        user.telegram_id = tg_id
        db.commit()
    return user


def _telegram_login_redirect(user: User) -> RedirectResponse:
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return RedirectResponse(url=f"{with_access_path(settings, '/login')}#token={access_token}", status_code=302)


def _complete_telegram_login(
    db: Session,
    request: Request,
    tg_id: str,
    *,
    mini: bool = False,
) -> User:
    user = _resolve_user_by_telegram_id(db, tg_id)
    client_ip = ip_restriction_service.get_client_ip(request)
    if not user:
        admin_notify_service.send_tg_login_unlinked(
            db,
            telegram_id=tg_id,
            remote_addr=client_ip,
            mini=mini,
            client_timezone=get_client_timezone_from_request(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Этот Telegram аккаунт не привязан ни к одному пользователю панели",
        )
    if user.role != UserRole.viewer:
        admin_notify_service.send_login_success(
            db,
            actor_username=user.username,
            remote_addr=client_ip,
            client_timezone=get_client_timezone_from_request(request),
            user_agent=user_agent_from_request(request),
            login_via="Telegram",
        )
    return user


def _oidc_login_error_redirect(message: str) -> RedirectResponse:
    return RedirectResponse(url=f"{with_access_path(settings, '/login')}?tg_error={quote(message)}", status_code=302)


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
        path=auth_cookie_path(settings),
    )


def _admin_requires_2fa(db: Session, user: User) -> bool:
    if user.role != UserRole.admin:
        return False
    return bool(user.totp_enabled or user_has_passkeys(db, user.id))


def _user_from_2fa_token(db: Session, temp_token: str, client_ip: str) -> User:
    username = decode_2fa_pending_token(temp_token)
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or user.role != UserRole.admin:
        auth_rate_limit_service.record_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код 2FA")
    if not _admin_requires_2fa(db, user):
        auth_rate_limit_service.record_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="2FA не настроена")
    return user


def _complete_2fa_login(user: User, db: Session, request: Request, response: Response, *, details: str) -> Token:
    client_ip = ip_restriction_service.get_client_ip(request)
    ip_restriction_service.record_login_attempt(client_ip, success=True)
    auth_rate_limit_service.record_success(client_ip)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="login_success",
            user_id=user.id,
            username=user.username,
            remote_addr=client_ip,
            details=details,
        )
    if user.role != UserRole.viewer:
        admin_notify_service.send_login_success(
            db,
            actor_username=user.username,
            remote_addr=client_ip,
            client_timezone=get_client_timezone_from_request(request),
            user_agent=user_agent_from_request(request),
        )
    db.commit()
    return _issue_token_pair(user, db, response, request)


def _issue_token_pair(
    user: User,
    db: Session,
    response: Response | None = None,
    request: Request | None = None,
) -> Token:
    access = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    raw_refresh, _ = create_refresh_token(db, user)
    web_session_id = active_web_session_service.generate_session_id()
    if response is not None:
        _set_refresh_cookie(response, raw_refresh)
    if request is not None:
        active_web_session_service.touch_active_web_session(
            db,
            user.username,
            request=request,
            session_id=web_session_id,
            force=True,
        )
    return Token(access_token=access, web_session_id=web_session_id)


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.refresh_token_cookie_name, path=auth_cookie_path(settings))


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
            user_agent=user_agent_from_request(request),
        )
        detail = "Неверный логин или пароль"
        if attempts > 2:
            detail += " (требуется капча)"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    if _admin_requires_2fa(db, user):
        return Login2FARequired(
            temp_token=create_2fa_pending_token(user.username),
            passkey_available=user_has_passkeys(db, user.id),
        )

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
            user_agent=user_agent_from_request(request),
        )
    return _issue_token_pair(user, db, response, request)


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
def telegram_login_config(request: Request, db: Session = Depends(get_db)):
    from app.services.feature_guards import get_feature_service

    if not get_feature_service().is_enabled("telegram"):
        return {
            "enabled": False,
            "bot_username": "",
            "max_age_seconds": 300,
            "oidc_enabled": False,
            "oidc_client_id": "",
            "legacy_enabled": False,
            "oidc_start_url": "",
            "auth_method": "none",
        }
    token, username, max_age = _get_telegram_auth_settings(db)
    oidc_enabled, oidc_client_id, oidc_secret = _get_telegram_oidc_settings(db)
    legacy_enabled = _legacy_login_enabled(db)
    oidc_ready = oidc_enabled and bool(oidc_client_id and oidc_secret)
    legacy_ready = legacy_enabled and bool(token and username)
    auth_method = "oidc" if oidc_enabled else ("legacy" if legacy_enabled else "none")
    root = resolve_request_url_root(request, behind_nginx=settings.behind_nginx).rstrip("/")
    return {
        "enabled": oidc_ready or legacy_ready,
        "auth_method": auth_method,
        "bot_username": username if legacy_ready else "",
        "max_age_seconds": max_age,
        "oidc_enabled": oidc_ready,
        "oidc_client_id": oidc_client_id if oidc_enabled else "",
        "legacy_enabled": legacy_ready,
        "oidc_start_url": f"{root}/api/auth/telegram/oidc/start" if oidc_ready else "",
    }


@router.get("/telegram/oidc/start")
def telegram_oidc_start(request: Request, db: Session = Depends(get_db)):
    from app.services.feature_guards import get_feature_service

    if not get_feature_service().is_enabled("telegram"):
        raise HTTPException(status_code=503, detail="Модуль Telegram отключён")
    oidc_enabled, client_id, client_secret = _get_telegram_oidc_settings(db)
    if not oidc_enabled or not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Telegram OpenID Connect не настроен")
    redirect_uri = _telegram_oidc_callback_url(request)
    state = secrets.token_urlsafe(24)
    code_verifier = pkce_verifier()
    auth_url = build_authorization_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_verifier=code_verifier,
    )
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/telegram/oidc/callback")
def telegram_oidc_callback(request: Request, db: Session = Depends(get_db)):
    from app.services.feature_guards import get_feature_service

    if not get_feature_service().is_enabled("telegram"):
        return _oidc_login_error_redirect("Модуль Telegram отключён")
    oidc_enabled, client_id, client_secret = _get_telegram_oidc_settings(db)
    if not oidc_enabled or not client_id or not client_secret:
        return _oidc_login_error_redirect("Telegram OpenID Connect не настроен")

    params = dict(request.query_params)
    error = (params.get("error") or "").strip()
    if error:
        description = (params.get("error_description") or error).strip()
        return _oidc_login_error_redirect(description or "Telegram OIDC отклонил вход")

    code = (params.get("code") or "").strip()
    state = (params.get("state") or "").strip()
    if not code or not state:
        return _oidc_login_error_redirect("Некорректный ответ Telegram OIDC")

    stored = pop_oidc_state(state)
    if not stored:
        return _oidc_login_error_redirect("Сессия Telegram OIDC истекла — попробуйте снова")

    redirect_uri = stored.get("redirect_uri") or _telegram_oidc_callback_url(request)
    code_verifier = stored.get("code_verifier") or ""
    try:
        token_payload = exchange_authorization_code(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
        id_token = str(token_payload.get("id_token") or "").strip()
        if not id_token:
            return _oidc_login_error_redirect("Telegram OIDC не вернул id_token")
        claims = verify_id_token(id_token, client_id=client_id)
        tg_id = telegram_id_from_claims(claims)
    except ValueError as exc:
        return _oidc_login_error_redirect(str(exc))
    except HTTPException:
        raise
    except Exception:
        return _oidc_login_error_redirect("Не удалось завершить вход через Telegram OIDC")

    try:
        user = _complete_telegram_login(db, request, tg_id, mini=False)
        return _telegram_login_redirect(user)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Ошибка входа через Telegram"
        return _oidc_login_error_redirect(detail)


@router.post("/telegram/oidc/token")
def telegram_oidc_token(payload: TelegramOidcTokenRequest, request: Request, db: Session = Depends(get_db)):
    from app.services.feature_guards import get_feature_service

    if not get_feature_service().is_enabled("telegram"):
        raise HTTPException(status_code=503, detail="Модуль Telegram отключён")
    oidc_enabled, client_id, client_secret = _get_telegram_oidc_settings(db)
    if not oidc_enabled or not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Telegram OpenID Connect не настроен")
    try:
        claims = verify_id_token(payload.id_token.strip(), client_id=client_id)
        tg_id = telegram_id_from_claims(claims)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    try:
        user = _complete_telegram_login(db, request, tg_id, mini=False)
    except HTTPException:
        raise
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/telegram")
def telegram_login_callback(request: Request, db: Session = Depends(get_db)):
    token, _, max_age = _get_telegram_auth_settings(db)
    if not token:
        raise HTTPException(status_code=503, detail="Telegram авторизация не настроена")
    if not _legacy_login_enabled(db):
        raise HTTPException(status_code=503, detail="Legacy Telegram Login отключён")
    payload = dict(request.query_params)
    ok, err = _verify_telegram_login(payload, token, max_age)
    if not ok:
        raise HTTPException(status_code=401, detail=err)
    tg_id = str(payload.get("id", ""))
    try:
        user = _complete_telegram_login(db, request, tg_id, mini=False)
        return _telegram_login_redirect(user)
    except HTTPException as exc:
        raise exc


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
    user = _user_from_2fa_token(db, payload.temp_token, client_ip)
    if not user.totp_enabled:
        auth_rate_limit_service.record_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="TOTP не настроен")
    if not verify_totp_code(user, payload.code):
        auth_rate_limit_service.record_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код 2FA")
    return _complete_2fa_login(user, db, request, response, details="2fa")


@router.post("/refresh", response_model=Token, response_model_exclude_none=True)
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
    session_id = active_web_session_service.get_session_id_from_request(request)
    if session_id:
        try:
            active_web_session_service.remove_active_web_session(db, session_id)
        except Exception:
            db.rollback()
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
    if should_scrub_env_after_password_change(current_user.username):
        scrub_admin_bootstrap_secret_from_env()
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


@router.post("/passkeys/register/options", response_model=PasskeyRegisterOptionsResponse)
def passkey_register_options(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    options = webauthn_service.registration_options(db, current_user, request)
    return PasskeyRegisterOptionsResponse(options=options)


@router.post("/passkeys/register/verify", response_model=PasskeyCredentialResponse)
def passkey_register_verify(
    payload: PasskeyRegisterVerifyRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = webauthn_service.registration_verify(
        db,
        current_user,
        request,
        credential=payload.credential,
        session_key=payload.session_key,
        nickname=payload.nickname,
    )
    if settings.audit_log_enabled:
        log_action(
            db,
            action="passkey_register",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=row.nickname,
        )
    return row


@router.get("/passkeys", response_model=PasskeyListResponse)
def passkey_list(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = list_passkeys(db, current_user.id)
    return PasskeyListResponse(credentials=rows, count=len(rows))


@router.patch("/passkeys/{credential_id}", response_model=PasskeyCredentialResponse)
def passkey_rename(
    credential_id: int,
    payload: PasskeyRenameRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return webauthn_service.rename_passkey(db, current_user, credential_id, payload.nickname)


@router.delete("/passkeys/{credential_id}", response_model=MessageResponse)
def passkey_delete(
    credential_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    webauthn_service.delete_passkey(db, current_user, credential_id)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="passkey_delete",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=str(credential_id),
        )
    return MessageResponse(message="Passkey удалён")


@router.post("/login/passkey/options", response_model=PasskeyRegisterOptionsResponse)
def passkey_login_options(
    payload: PasskeyAuthOptionsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    client_ip = ip_restriction_service.get_client_ip(request)
    auth_rate_limit_service.check(client_ip)
    user = _user_from_2fa_token(db, payload.temp_token, client_ip)
    if not user_has_passkeys(db, user.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkeys не настроены")
    options = webauthn_service.authentication_options(db, user, request)
    return PasskeyRegisterOptionsResponse(options=options)


@router.post("/login/passkey/verify", response_model=Token)
def passkey_login_verify(
    payload: PasskeyAuthVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    client_ip = ip_restriction_service.get_client_ip(request)
    auth_rate_limit_service.check(client_ip)
    user = _user_from_2fa_token(db, payload.temp_token, client_ip)
    try:
        webauthn_service.authentication_verify(
            db,
            user,
            request,
            credential=payload.credential,
            session_key=payload.session_key,
        )
    except HTTPException:
        auth_rate_limit_service.record_failure(client_ip)
        if settings.audit_log_enabled:
            log_action(
                db,
                action="passkey_login_failed",
                user_id=user.id,
                username=user.username,
                remote_addr=client_ip,
            )
        raise
    return _complete_2fa_login(user, db, request, response, details="passkey")
