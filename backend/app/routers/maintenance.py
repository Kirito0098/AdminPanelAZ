from pathlib import Path
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
import json

from app.models import DEFAULT_TG_NOTIFY_EVENTS, AppSetting, User
from app.schemas import (
    AdminNotifyEventItem,
    AdminNotifyEventTestRequest,
    AdminNotifySettingsResponse,
    AdminNotifySettingsUpdate,
    BackgroundTaskResponse,
    GeoIpStatusResponse,
    MessageResponse,
    NocReportPreviewRequest,
    ServiceRestartRequest,
    TelegramLinkCodeResponse,
    TelegramSettingsResponse,
    TelegramSettingsUpdate,
    VpnNetworkDomainSslStatusResponse,
    VpnNetworkEnvRow,
    VpnNetworkPortStatusResponse,
    VpnNetworkPublishModeInfo,
    VpnNetworkPublishRequest,
    VpnNetworkSettingsResponse,
)
from app.services.admin_notify import (
    TG_NOTIFY_EVENT_LABELS,
    admin_notify_service,
    send_notify_event_preview,
)
from app.services.background_tasks import background_task_service
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.notify_time import get_client_timezone_from_request
from app.config import get_settings
from app.services.active_web_session import active_web_session_service
from app.services.env_file import EnvFileService
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.noc_report import send_noc_report_preview, send_weekly_image_preview
from app.services.action_log import log_action
from app.services.panel_publish_info import (
    build_panel_publish_context,
    build_vpn_network_publish_modes,
    discover_ssl_certificate_candidates,
    build_uvicorn_publish_warnings,
    inspect_tcp_port,
    is_nginx_installed,
    letsencrypt_cert_paths,
    letsencrypt_exists_for_domain,
    panel_restart_command,
    server_primary_ip,
    resolve_publish_ssl_paths,
    resolve_request_url_root,
)
from app.services.telegram import send_tg_message
from app.services.telegram_recipients import (
    filter_notify_recipients,
    get_notify_recipient_user_ids,
    get_setting_chat_ids,
    join_chat_ids,
    join_user_ids,
    parse_chat_ids,
    parse_user_ids,
    resolve_notify_recipient_users,
)
from app.services.telegram_api import delete_webhook_sync, set_webhook_sync
from app.services.telegram_link import create_link_code

router = APIRouter(tags=["maintenance"])


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


@router.post("/settings/run-doall", status_code=status.HTTP_202_ACCEPTED)
def run_doall(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    active = background_task_service.find_active_task("run_doall")
    if active:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "doall.sh уже выполняется",
                "active_task_id": active.id,
            },
        )

    client_timezone = get_client_timezone_from_request(request)

    def _callable(progress_updater=None):
        from app.database import SessionLocal

        worker_db = SessionLocal()
        try:
            adapter = get_active_adapter(worker_db)
            result = background_task_service.task_run_doall(adapter, progress_updater)
            node = get_active_node(worker_db)
            admin_notify_service.send_settings_change(
                worker_db,
                actor_username=admin.username,
                settings_key="settings_run_doall",
                node_id=node.id,
                node_name=node.name,
                client_timezone=client_timezone,
            )
            return result
        finally:
            worker_db.close()

    task = background_task_service.enqueue_background_task(
        "run_doall",
        _callable,
        created_by_username=admin.username,
        queued_message="Запуск doall поставлен в очередь",
    )
    return background_task_service.build_accepted_payload(task, "Скрипт doall запущен в фоне.")


@router.post("/settings/restart-service", response_model=MessageResponse)
def restart_service(
    payload: ServiceRestartRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    output = get_active_adapter(db).restart_service(payload.service_name)
    node = get_active_node(db)
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_restart_service",
        subject_name=payload.service_name,
        node_id=node.id,
        node_name=node.name,
        client_timezone=get_client_timezone_from_request(request),
    )
    return MessageResponse(message=f"Служба {payload.service_name} перезапущена", detail=output)


def _normalize_bot_username(value: str) -> str:
    return value.strip().lstrip("@")


def _ensure_webhook_secret(db: Session) -> str:
    secret = _get_setting(db, "telegram_webhook_secret")
    if not secret:
        secret = secrets.token_urlsafe(32)
        _set_setting(db, "telegram_webhook_secret", secret)
    return secret


def _webhook_url(request: Request, secret: str) -> str:
    root = resolve_request_url_root(request, behind_nginx=get_settings().behind_nginx).rstrip("/")
    return f"{root}/api/telegram/webhook/{secret}"


def _telegram_settings_response(db: Session, request: Request) -> TelegramSettingsResponse:
    max_age_raw = _get_setting(db, "telegram_auth_max_age_seconds")
    max_age = int(max_age_raw) if max_age_raw.isdigit() else 300
    max_age = max(30, min(max_age, 86400))
    root = resolve_request_url_root(request, behind_nginx=get_settings().behind_nginx).rstrip("/")
    webhook_set_at = _get_setting(db, "telegram_webhook_set_at")
    webhook_secret = _get_setting(db, "telegram_webhook_secret")
    bot_token_set = bool(_get_setting(db, "telegram_bot_token"))
    bot_username = _get_setting(db, "telegram_bot_username")
    oidc_enabled = _get_setting(db, "telegram_oidc_enabled", "false") == "true"
    oidc_client_id = _get_setting(db, "telegram_oidc_client_id")
    oidc_client_secret_set = bool(_get_setting(db, "telegram_oidc_client_secret"))
    legacy_login_enabled = _get_setting(db, "telegram_legacy_login_enabled", "true") != "false" and not oidc_enabled
    oidc_ready = oidc_enabled and bool(oidc_client_id and oidc_client_secret_set)
    legacy_ready = legacy_login_enabled and bot_token_set and bool(bot_username)
    auth_method: str = "oidc" if oidc_enabled else ("legacy" if legacy_login_enabled else "none")
    chat_ids = get_setting_chat_ids(lambda key, default="": _get_setting(db, key, default))
    return TelegramSettingsResponse(
        bot_token_set=bot_token_set,
        bot_username=bot_username,
        auth_max_age_seconds=max_age,
        mini_app_url=f"{root}/api/tg-mini",
        chat_id=join_chat_ids(chat_ids),
        chat_ids=chat_ids,
        notify_on_backup=_get_setting(db, "backup_telegram_enabled", "false") == "true",
        notify_enabled=_get_setting(db, "telegram_notify_enabled", "false") == "true",
        interactive_enabled=_get_setting(db, "telegram_bot_interactive_enabled", "false") == "true",
        webhook_registered=bool(webhook_set_at),
        webhook_secret_set=bool(webhook_secret),
        webhook_set_at=webhook_set_at,
        oidc_enabled=oidc_enabled,
        oidc_client_id=oidc_client_id,
        oidc_client_secret_set=oidc_client_secret_set,
        oidc_callback_url=f"{root}/api/auth/telegram/oidc/callback",
        oidc_trusted_origin=root,
        legacy_login_enabled=legacy_login_enabled,
        auth_method=auth_method,
        login_ready=oidc_ready or legacy_ready,
    )


@router.get("/settings/telegram", response_model=TelegramSettingsResponse)
def get_telegram_settings(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return _telegram_settings_response(db, request)


@router.patch("/settings/telegram", response_model=TelegramSettingsResponse)
def update_telegram_settings(
    payload: TelegramSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if payload.bot_token is not None:
        _set_setting(db, "telegram_bot_token", payload.bot_token.strip())
    if payload.bot_username is not None:
        _set_setting(db, "telegram_bot_username", _normalize_bot_username(payload.bot_username))
    if payload.auth_max_age_seconds is not None:
        _set_setting(db, "telegram_auth_max_age_seconds", str(payload.auth_max_age_seconds))
    if payload.chat_ids is not None:
        _set_setting(db, "telegram_chat_id", join_chat_ids(payload.chat_ids))
    elif payload.chat_id is not None:
        _set_setting(db, "telegram_chat_id", join_chat_ids(parse_chat_ids(payload.chat_id)))
    if payload.notify_enabled is not None:
        _set_setting(db, "telegram_notify_enabled", "true" if payload.notify_enabled else "false")
    if payload.notify_on_backup is not None:
        _set_setting(db, "backup_telegram_enabled", "true" if payload.notify_on_backup else "false")
    if payload.interactive_enabled is not None:
        _set_setting(db, "telegram_bot_interactive_enabled", "true" if payload.interactive_enabled else "false")
        if payload.interactive_enabled:
            _ensure_webhook_secret(db)
        else:
            token = _get_setting(db, "telegram_bot_token")
            if token:
                delete_webhook_sync(token)
            _set_setting(db, "telegram_webhook_set_at", "")
    if payload.auth_method is not None:
        if payload.auth_method == "oidc":
            _set_setting(db, "telegram_oidc_enabled", "true")
            _set_setting(db, "telegram_legacy_login_enabled", "false")
        else:
            _set_setting(db, "telegram_oidc_enabled", "false")
            _set_setting(db, "telegram_legacy_login_enabled", "true")
    if payload.oidc_enabled is not None:
        _set_setting(db, "telegram_oidc_enabled", "true" if payload.oidc_enabled else "false")
        if payload.oidc_enabled:
            _set_setting(db, "telegram_legacy_login_enabled", "false")
    if payload.oidc_client_id is not None:
        _set_setting(db, "telegram_oidc_client_id", payload.oidc_client_id.strip())
    if payload.oidc_client_secret is not None:
        _set_setting(db, "telegram_oidc_client_secret", payload.oidc_client_secret.strip())
    if payload.legacy_login_enabled is not None and payload.auth_method is None:
        if payload.legacy_login_enabled:
            _set_setting(db, "telegram_oidc_enabled", "false")
            _set_setting(db, "telegram_legacy_login_enabled", "true")
        else:
            _set_setting(db, "telegram_legacy_login_enabled", "false")
    db.commit()
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_telegram_auth_update",
        client_timezone=get_client_timezone_from_request(request),
    )
    return _telegram_settings_response(db, request)


def _admin_notify_settings_response(db: Session, user: User) -> AdminNotifySettingsResponse:
    merged = user.merged_tg_notify_events()
    recipient_user_ids = get_notify_recipient_user_ids(lambda key, default="": _get_setting(db, key, default)) or []
    return AdminNotifySettingsResponse(
        telegram_id=user.telegram_id or "",
        recipient_user_ids=recipient_user_ids,
        notify_enabled=_get_setting(db, "telegram_notify_enabled", "false") == "true",
        bot_token_set=bool(_get_setting(db, "telegram_bot_token")),
        events=[
            AdminNotifyEventItem(key=key, label=label, enabled=merged.get(key, False))
            for key, label in TG_NOTIFY_EVENT_LABELS
        ],
    )


def _notify_recipients_for_tests(db: Session, admin: User) -> list[User]:
    recipients = resolve_notify_recipient_users(db, lambda key, default="": _get_setting(db, key, default))
    if recipients:
        return recipients
    if admin.telegram_id:
        return [admin]
    return []


def _send_test_message_to_recipients(db: Session, admin: User, text: str) -> tuple[int, int]:
    bot_token = _get_setting(db, "telegram_bot_token")
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен бота не настроен")
    recipients = _notify_recipients_for_tests(db, admin)
    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выберите получателей с Telegram ID в настройках уведомлений",
        )
    sent = 0
    for user in recipients:
        if user.telegram_id and send_tg_message(bot_token, user.telegram_id, text, run_async=False):
            sent += 1
    if sent == 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")
    return sent, len(recipients)


@router.get("/settings/admin-notify", response_model=AdminNotifySettingsResponse)
def get_admin_notify_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return _admin_notify_settings_response(db, admin)


@router.patch("/settings/admin-notify", response_model=AdminNotifySettingsResponse)
def update_admin_notify_settings(
    payload: AdminNotifySettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if payload.recipient_user_ids is not None:
        _set_setting(db, "telegram_notify_recipient_user_ids", join_user_ids(payload.recipient_user_ids))
    if payload.telegram_id is not None:
        tg_id = payload.telegram_id.strip()
        if tg_id:
            existing = db.query(User).filter(User.telegram_id == tg_id, User.id != admin.id).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Этот Telegram ID уже привязан к другому пользователю",
                )
            admin.telegram_id = tg_id
        else:
            admin.telegram_id = None
    if payload.events is not None:
        merged = admin.merged_tg_notify_events()
        for key in DEFAULT_TG_NOTIFY_EVENTS:
            if key in payload.events:
                merged[key] = bool(payload.events[key])
        admin.tg_notify_events = json.dumps(merged)
    db.commit()
    db.refresh(admin)
    return _admin_notify_settings_response(db, admin)


@router.post("/settings/admin-notify/test", response_model=MessageResponse)
def test_admin_notify(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    merged = admin.merged_tg_notify_events()
    enabled = [label for key, label in TG_NOTIFY_EVENT_LABELS if merged.get(key)]
    events_text = "\n".join(f"  ✓ {item}" for item in enabled) if enabled else "  (нет включённых событий)"
    text = (
        "🔔 <b>Тест уведомлений AdminPanelAZ</b>\n\n"
        f"Аккаунт: <code>{admin.username}</code>\n\n"
        f"Включённые события:\n{events_text}"
    )
    sent, total = _send_test_message_to_recipients(db, admin, text)
    return MessageResponse(message=f"Тестовое сообщение отправлено ({sent} из {total})")


@router.post("/settings/admin-notify/test-event", response_model=MessageResponse)
def test_admin_notify_event(
    payload: AdminNotifyEventTestRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    event_key = payload.event.strip()
    if event_key not in DEFAULT_TG_NOTIFY_EVENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный тип события")
    bot_token = _get_setting(db, "telegram_bot_token")
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен бота не настроен")
    recipients = _notify_recipients_for_tests(db, admin)
    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выберите получателей с Telegram ID в настройках уведомлений",
        )

    sent = 0
    for user in recipients:
        if not user.telegram_id:
            continue
        if event_key == "noc_report":
            ok = send_noc_report_preview(
                db,
                period="daily",
                telegram_id=user.telegram_id,
                bot_token=bot_token,
            )
        else:
            ok = send_notify_event_preview(
                db,
                event_key=event_key,
                telegram_id=user.telegram_id,
                bot_token=bot_token,
                actor_username=user.username,
            )
        if ok:
            sent += 1
    if sent == 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")

    label = dict(TG_NOTIFY_EVENT_LABELS).get(event_key, event_key)
    return MessageResponse(message=f"Пример «{label}» отправлен ({sent} из {len(recipients)})")


@router.post("/settings/admin-notify/test-noc-report", response_model=MessageResponse)
def test_noc_report_preview(
    payload: NocReportPreviewRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("telegram"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=module_disabled_message("telegram"))
    bot_token = _get_setting(db, "telegram_bot_token")
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен бота не настроен")
    recipients = _notify_recipients_for_tests(db, admin)
    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выберите получателей с Telegram ID в настройках уведомлений",
        )

    period = payload.period if payload.period in {"daily", "weekly"} else "daily"
    sent = 0
    for user in recipients:
        if not user.telegram_id:
            continue
        if send_noc_report_preview(
            db,
            period=period,
            telegram_id=user.telegram_id,
            bot_token=bot_token,
        ):
            sent += 1
    if sent == 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")

    label = "еженедельная" if period == "weekly" else "ежедневная"
    return MessageResponse(message=f"NOC сводка ({label}) отправлена ({sent} из {len(recipients)})")


@router.post("/settings/admin-notify/test-noc-image", response_model=MessageResponse)
def test_noc_weekly_image_preview(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if not get_feature_service().is_enabled("telegram"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=module_disabled_message("telegram"))
    bot_token = _get_setting(db, "telegram_bot_token")
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен бота не настроен")
    recipients = _notify_recipients_for_tests(db, admin)
    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выберите получателей с Telegram ID в настройках уведомлений",
        )

    sent = 0
    for user in recipients:
        if not user.telegram_id:
            continue
        if send_weekly_image_preview(db, telegram_id=user.telegram_id, bot_token=bot_token):
            sent += 1
    if sent == 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить изображение в Telegram")

    return MessageResponse(message=f"NOC weekly изображение отправлено ({sent} из {len(recipients)})")


@router.post("/settings/admin-notify/test-noc-pdf", response_model=MessageResponse)
def test_noc_weekly_pdf_preview_legacy(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Legacy alias — weekly report is now sent as PNG."""
    return test_noc_weekly_image_preview(db=db, admin=admin)


@router.post("/settings/telegram/test", response_model=MessageResponse)
def test_telegram(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    bot_token = _get_setting(db, "telegram_bot_token")
    chat_ids = get_setting_chat_ids(lambda key, default="": _get_setting(db, key, default))
    if not bot_token or not chat_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите токен бота и получателей бэкапа")
    sent = 0
    for chat_id in chat_ids:
        if send_tg_message(
            bot_token,
            chat_id,
            "✅ <b>AdminPanelAZ</b>: тестовое уведомление Telegram",
            run_async=False,
        ):
            sent += 1
    if sent == 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")
    return MessageResponse(message=f"Тестовое сообщение отправлено ({sent} из {len(chat_ids)})")


@router.post("/settings/telegram/webhook/register", response_model=TelegramSettingsResponse)
def register_telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("telegram"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=module_disabled_message("telegram"))
    bot_token = _get_setting(db, "telegram_bot_token")
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен бота не настроен")
    if _get_setting(db, "telegram_bot_interactive_enabled", "false") != "true":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Интерактивный бот не включён")

    secret = _ensure_webhook_secret(db)
    url = _webhook_url(request, secret)
    ok, error = set_webhook_sync(bot_token, url, secret_token=secret)
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"setWebhook: {error}")

    from app.services.telegram_bot_handlers.menu import build_bot_commands
    from app.services.telegram_api import reset_chat_menu_button_sync, set_my_commands_sync

    cmd_ok, cmd_error = set_my_commands_sync(bot_token, build_bot_commands())
    if not cmd_ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"setMyCommands: {cmd_error}")

    menu_ok, menu_error = reset_chat_menu_button_sync(bot_token)
    if not menu_ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"setChatMenuButton: {menu_error}")

    _set_setting(db, "telegram_webhook_set_at", datetime.now(timezone.utc).isoformat())
    db.commit()
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_telegram_auth_update",
        client_timezone=get_client_timezone_from_request(request),
    )
    return _telegram_settings_response(db, request)


@router.delete("/settings/telegram/webhook", response_model=TelegramSettingsResponse)
def unregister_telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    bot_token = _get_setting(db, "telegram_bot_token")
    if bot_token:
        ok, error = delete_webhook_sync(bot_token)
        if not ok:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"deleteWebhook: {error}")
        from app.services.telegram_api import reset_chat_menu_button_sync

        menu_ok, menu_error = reset_chat_menu_button_sync(bot_token)
        if not menu_ok:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"setChatMenuButton: {menu_error}")
    _set_setting(db, "telegram_webhook_set_at", "")
    db.commit()
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_telegram_auth_update",
        client_timezone=get_client_timezone_from_request(request),
    )
    return _telegram_settings_response(db, request)


@router.get("/settings/vpn-network", response_model=VpnNetworkSettingsResponse)
def get_vpn_network_settings(
    request: Request,
    _: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("vpn_network"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("vpn_network"),
        )
    settings = get_settings()
    env_path = Path(__file__).resolve().parents[2] / ".env"
    env = EnvFileService(env_path)
    ctx = build_panel_publish_context(
        get_env_value=env.get_env_value,
        request_url=resolve_request_url_root(request, behind_nginx=settings.behind_nginx),
        settings=settings,
    )
    publish_modes = [VpnNetworkPublishModeInfo(**row) for row in build_vpn_network_publish_modes()]
    domain = env.get_env_value("DOMAIN", "")
    ssl_cert = env.get_env_value("SSL_CERT", "")
    ssl_key = env.get_env_value("SSL_KEY", "")
    suggestions = discover_ssl_certificate_candidates(
        domain=domain,
        ssl_cert=ssl_cert,
        ssl_key=ssl_key,
    )
    known_cert = ssl_cert if ssl_cert and Path(ssl_cert).is_file() else None
    known_key = ssl_key if ssl_key and Path(ssl_key).is_file() else None
    if not known_cert and suggestions:
        known_cert = suggestions[0]["cert"]
        known_key = suggestions[0]["key"]
    uvicorn_warnings = build_uvicorn_publish_warnings(
        domain=domain,
        backend_port=ctx["backend_port"],
        ssl_cert_suggestions=suggestions,
    )
    return VpnNetworkSettingsResponse(
        mode_key=ctx["mode_key"],
        mode_title=ctx["mode_title"],
        bullet_points=ctx["bullet_points"],
        internal_url=ctx["internal_url"],
        primary_urls=ctx["primary_urls"],
        env_rows=[VpnNetworkEnvRow(**row) for row in ctx["env_rows"]],
        backend_port=ctx["backend_port"],
        publish_modes=publish_modes,
        active_publish_mode=ctx.get("active_publish_mode"),
        known_ssl_cert=known_cert,
        known_ssl_key=known_key,
        ssl_cert_suggestions=suggestions,
        nginx_installed=is_nginx_installed(),
        panel_restart_command=panel_restart_command(),
        uvicorn_publish_warnings=uvicorn_warnings,
        server_primary_ip=server_primary_ip(),
    )


@router.get("/settings/vpn-network/domain-ssl", response_model=VpnNetworkDomainSslStatusResponse)
def get_vpn_network_domain_ssl(
    domain: str,
    _: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("vpn_network"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("vpn_network"),
        )
    domain_host = (domain or "").strip().split(":")[0]
    if not domain_host:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите домен")
    cert, key = letsencrypt_cert_paths(domain_host)
    has_le = letsencrypt_exists_for_domain(domain_host)
    return VpnNetworkDomainSslStatusResponse(
        domain=domain_host,
        has_letsencrypt=has_le,
        cert=cert if has_le else None,
        key=key if has_le else None,
    )


@router.get("/settings/vpn-network/port-status", response_model=VpnNetworkPortStatusResponse)
def get_vpn_network_port_status(
    port: int,
    role: str = "backend",
    _: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("vpn_network"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("vpn_network"),
        )
    allowed_roles = {"backend", "nginx_https", "nginx_http"}
    if role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная роль порта")
    result = inspect_tcp_port(port, role=role)
    return VpnNetworkPortStatusResponse(**result)


@router.post("/settings/vpn-network/publish", status_code=status.HTTP_202_ACCEPTED, response_model=BackgroundTaskResponse)
def publish_vpn_network(
    payload: VpnNetworkPublishRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not get_feature_service().is_enabled("vpn_network"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("vpn_network"),
        )

    if payload.mode in {"nginx_le", "uvicorn_le"} and not (payload.domain or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DOMAIN обязателен для Let's Encrypt")

    env_path = Path(__file__).resolve().parents[2] / ".env"
    env = EnvFileService(env_path)

    if payload.mode in {"nginx_custom", "uvicorn_custom"}:
        cert, key = resolve_publish_ssl_paths(
            ssl_cert=payload.ssl_cert,
            ssl_key=payload.ssl_key,
            domain=payload.domain,
            get_env_value=env.get_env_value,
        )
        if not cert or not key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Укажите пути к сертификату и ключу или задайте DOMAIN для Let's Encrypt",
            )
        if not Path(cert).is_file() or not Path(key).is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Файлы сертификата не найдены: {cert}, {key}",
            )
        payload.ssl_cert = cert
        payload.ssl_key = key

    uvicorn_modes = {"uvicorn_le", "uvicorn_selfsigned", "uvicorn_custom"}
    if payload.mode not in uvicorn_modes:
        if payload.backend_port == payload.https_public_port or payload.backend_port == payload.http_acme_port:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="BACKEND_PORT конфликтует с публичными портами")
        if payload.http_acme_port == payload.https_public_port:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="HTTP_ACME_PORT совпадает с HTTPS_PUBLIC_PORT")

    active = background_task_service.find_active_task("vpn_network_publish")
    if active:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Публикация панели уже выполняется",
                "active_task_id": active.id,
            },
        )

    task_payload = payload.model_dump()

    def _callable(progress_updater=None):
        return background_task_service.task_vpn_network_publish(task_payload, progress_updater)

    task = background_task_service.enqueue_background_task(
        "vpn_network_publish",
        _callable,
        created_by_username=admin.username,
        queued_message="Публикация панели поставлена в очередь",
    )

    from app.services.ip_restriction import ip_restriction_service

    if get_settings().audit_log_enabled:
        log_action(
            db,
            action="settings_vpn_network_publish",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"mode={payload.mode}, port={payload.backend_port}",
        )

    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_vpn_network_publish",
        details=f"mode={payload.mode}",
        client_timezone=get_client_timezone_from_request(request),
    )

    return background_task_service.build_accepted_payload(
        task,
        "Публикация панели запущена в фоне.",
    )


@router.get("/maintenance/session-stats")
def session_stats(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    cfg = get_settings()
    return {
        "active_web_sessions_count": active_web_session_service.count_active_sessions(db),
        "tracking_enabled": cfg.active_web_session_tracking_enabled,
        "nightly_idle_restart_enabled": cfg.nightly_idle_restart_enabled,
        "active_web_session_ttl_seconds": cfg.active_web_session_ttl_seconds,
        "nightly_idle_restart_cron": cfg.nightly_idle_restart_cron,
    }


@router.get("/maintenance/geoip-status", response_model=GeoIpStatusResponse)
def geoip_status(_: User = Depends(require_admin)):
    from app.services.ip_geo import get_geoip_status

    return get_geoip_status()
