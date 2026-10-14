import html
import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import get_settings
from app.database import get_db
from app.models import DEFAULT_TG_NOTIFY_EVENTS, Node, User
from app.schemas import (
    AdminNotifyEventItem,
    AdminNotifyEventTestRequest,
    AdminNotifyGroupInfo,
    AdminNotifySettingsResponse,
    AdminNotifySettingsUpdate,
    MessageResponse,
    NocReportPreviewRequest,
    TelegramRelayCheck,
    TelegramRelayNode,
    TelegramRelayUpdate,
    TelegramSettingsResponse,
    TelegramSettingsUpdate,
)
from app.services.admin_notify import (
    TG_NOTIFY_EVENT_GROUPS,
    TG_NOTIFY_EVENT_GROUP_BY_KEY,
    TG_NOTIFY_EVENT_LABELS,
    admin_notify_service,
    send_notify_event_preview,
)
from app.services.app_setting_store import _get_setting, _set_setting
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.noc_report import send_noc_report_preview, send_weekly_image_preview
from app.services.notify_time import get_client_timezone_from_request
from app.services.panel_publish_info import resolve_request_url_root
from app.services.telegram import send_tg_message
from app.services.telegram_api import (
    delete_webhook_sync,
    reset_chat_menu_button_sync,
    set_my_commands_sync,
    set_webhook_sync,
)
from app.services.telegram_bot_command_rate_limit import get_bot_command_rate_limits, set_bot_command_rate_limits
from app.services.telegram_link import notify_telegram_unlinked
from app.services.telegram_transport import (
    RELAY_CHECK_TIMEOUT,
    RELAY_NODES_SETTING,
    TelegramRelayError,
    call_via_node,
    mark_relay_node_failed,
    parse_relay_node_ids,
    relay_node_ineligible_reason,
)
from app.services.telegram_recipients import (
    get_notify_recipient_user_ids,
    get_setting_chat_ids,
    join_chat_ids,
    join_user_ids,
    parse_chat_ids,
    resolve_notify_recipient_users,
)

router = APIRouter(tags=["maintenance"])


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


def _configure_bot_menu(token: str) -> None:
    from app.services.telegram_bot_handlers.menu import build_bot_commands

    for ok, error in (set_my_commands_sync(token, build_bot_commands()), reset_chat_menu_button_sync(token)):
        if not ok:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error)


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
    bot_limits = get_bot_command_rate_limits(db)
    relay_nodes = [
        TelegramRelayNode(id=node.id, name=node.name, unavailable_reason=relay_node_ineligible_reason(node))
        for node in db.query(Node).order_by(Node.name).all()
        if not node.is_local and (node.node_kind or "vpn") == "vpn"
    ]
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
        bot_command_rate_max=bot_limits["max_requests"],
        bot_command_rate_window_seconds=bot_limits["window_seconds"],
        bot_command_rate_limit_enabled=get_settings().telegram_bot_command_rate_limit_enabled,
        relay_node_ids=parse_relay_node_ids(_get_setting(db, RELAY_NODES_SETTING)),
        relay_nodes=relay_nodes,
        relay_last_ok_at=_get_setting(db, "telegram_relay_last_ok_at"),
        relay_last_error=_get_setting(db, "telegram_relay_last_error"),
        relay_last_node=_get_setting(db, "telegram_relay_last_node"),
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
    if payload.bot_command_rate_max is not None or payload.bot_command_rate_window_seconds is not None:
        set_bot_command_rate_limits(
            db,
            max_requests=payload.bot_command_rate_max,
            window_seconds=payload.bot_command_rate_window_seconds,
        )
    db.commit()
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_telegram_auth_update",
        client_timezone=get_client_timezone_from_request(request),
    )
    return _telegram_settings_response(db, request)


def _admin_notify_settings_response(db: Session, user: User) -> AdminNotifySettingsResponse:
    from app.services.node_status_notify import get_node_offline_grace_seconds

    merged = user.merged_tg_notify_events()
    recipient_user_ids = get_notify_recipient_user_ids(lambda key, default="": _get_setting(db, key, default)) or []
    return AdminNotifySettingsResponse(
        telegram_id=user.telegram_id or "",
        recipient_user_ids=recipient_user_ids,
        notify_enabled=_get_setting(db, "telegram_notify_enabled", "false") == "true",
        bot_token_set=bool(_get_setting(db, "telegram_bot_token")),
        events=[
            AdminNotifyEventItem(
                key=key,
                label=label,
                enabled=merged.get(key, False),
                group=TG_NOTIFY_EVENT_GROUP_BY_KEY.get(key, ""),
            )
            for key, label in TG_NOTIFY_EVENT_LABELS
        ],
        groups=[
            AdminNotifyGroupInfo(group=group_id, title=title, icon=icon, keys=list(keys))
            for group_id, title, icon, keys in TG_NOTIFY_EVENT_GROUPS
        ],
        node_offline_grace_seconds=get_node_offline_grace_seconds(db),
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
    old_telegram_id = admin.telegram_id
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
                merged[key] = payload.events[key]
        admin.tg_notify_events = json.dumps(merged)
    if payload.node_offline_grace_seconds is not None:
        from app.services.node_status_notify import set_node_offline_grace_seconds

        set_node_offline_grace_seconds(db, payload.node_offline_grace_seconds)
    db.commit()
    db.refresh(admin)
    if payload.telegram_id is not None:
        notify_telegram_unlinked(
            db,
            old_telegram_id=old_telegram_id,
            new_telegram_id=admin.telegram_id,
            username=admin.username,
        )
    return _admin_notify_settings_response(db, admin)


@router.post("/settings/admin-notify/test", response_model=MessageResponse)
def test_admin_notify(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    merged = admin.merged_tg_notify_events()
    enabled = [label for key, label in TG_NOTIFY_EVENT_LABELS if merged.get(key)]
    events_text = "\n".join(f"  ✓ {item}" for item in enabled) if enabled else "  (нет включённых событий)"
    text = (
        "🔔 <b>Тест уведомлений AdminPanelAZ</b>\n\n"
        f"Аккаунт: <code>{html.escape(admin.username)}</code>\n\n"
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

    sent = 0
    for user in recipients:
        if not user.telegram_id:
            continue
        if send_noc_report_preview(
            db,
            period=payload.period,
            telegram_id=user.telegram_id,
            bot_token=bot_token,
        ):
            sent += 1
    if sent == 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")

    label = "еженедельная" if payload.period == "weekly" else "ежедневная"
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
    if _get_setting(db, RELAY_NODES_SETTING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Включена связь через узел: webhook не нужен"
        )

    secret = _ensure_webhook_secret(db)
    url = _webhook_url(request, secret)
    ok, error = set_webhook_sync(bot_token, url, secret_token=secret)
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error)

    _configure_bot_menu(bot_token)
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
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error)
        menu_ok, menu_error = reset_chat_menu_button_sync(bot_token)
        if not menu_ok:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=menu_error)
    _set_setting(db, "telegram_webhook_set_at", "")
    db.commit()
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_telegram_auth_update",
        client_timezone=get_client_timezone_from_request(request),
    )
    return _telegram_settings_response(db, request)


def _check_relay_node(token: str, node: Node) -> TelegramRelayCheck:
    try:
        envelope, _name = call_via_node(
            node.id,
            lambda adapter: adapter.telegram_bot_api(
                token, "getMe", b"{}", "application/json", timeout=RELAY_CHECK_TIMEOUT
            ),
        )
    except TelegramRelayError as exc:
        mark_relay_node_failed(node.id)
        return TelegramRelayCheck(id=node.id, name=node.name, ok=False, error=str(exc))
    body = envelope["body"]
    if not body.get("ok"):
        return TelegramRelayCheck(
            id=node.id, name=node.name, ok=False, error=str(body.get("description") or "Telegram отклонил токен бота")
        )
    return TelegramRelayCheck(id=node.id, name=node.name, ok=True)


@router.put("/settings/telegram/relay", response_model=TelegramSettingsResponse)
def update_telegram_relay(
    payload: TelegramRelayUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    checks: list[TelegramRelayCheck] = []
    if not payload.node_ids:
        _set_setting(db, RELAY_NODES_SETTING, "")
    else:
        nodes = []
        for node_id in payload.node_ids:
            node = db.get(Node, node_id)
            if node is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Узел #{node_id} не найден")
            reason = relay_node_ineligible_reason(node)
            if reason:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"«{node.name}»: {reason}")
            nodes.append(node)
        token = _get_setting(db, "telegram_bot_token")
        if token:
            checks = [_check_relay_node(token, node) for node in nodes]
            if not any(check.ok for check in checks):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Ни один узел не достучался до Telegram: " + "; ".join(c.error for c in checks),
                )
        previous = _get_setting(db, RELAY_NODES_SETTING)
        root = resolve_request_url_root(request, behind_nginx=get_settings().behind_nginx).rstrip("/")
        _set_setting(db, RELAY_NODES_SETTING, ",".join(str(node_id) for node_id in payload.node_ids))
        _set_setting(db, "telegram_mini_app_url", f"{root}/api/tg-mini")
        _set_setting(db, "telegram_relay_last_error", "")
        db.commit()
        try:
            if token:
                ok, error = delete_webhook_sync(token)
                if not ok:
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error)
                _configure_bot_menu(token)
        except HTTPException:
            _set_setting(db, RELAY_NODES_SETTING, previous)
            db.commit()
            raise
    _set_setting(db, "telegram_webhook_set_at", "")
    db.commit()
    admin_notify_service.send_settings_change(
        db,
        actor_username=admin.username,
        settings_key="settings_telegram_auth_update",
        client_timezone=get_client_timezone_from_request(request),
    )
    response = _telegram_settings_response(db, request)
    response.relay_check = checks
    return response
