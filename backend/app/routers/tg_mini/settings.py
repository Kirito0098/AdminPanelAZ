"""Settings endpoints for Telegram Mini App."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_tg_mini_user, require_tg_mini_admin
from app.database import get_db
from app.models import DEFAULT_TG_NOTIFY_EVENTS, User, UserRole
from app.routers.settings_telegram import (
    _admin_notify_settings_response,
    _send_test_message_to_recipients,
    _telegram_settings_response,
    update_telegram_settings,
)
from app.schemas import (
    AdminNotifyEventItem,
    AdminNotifySettingsResponse,
    AdminNotifySettingsUpdate,
    EffectiveVisibleVpnProfilesResponse,
    MessageResponse,
    TelegramSettingsResponse,
    TelegramSettingsUpdate,
    VisibleVpnProfilesPolicy,
)
from app.services.admin_notify import (
    PERSONAL_OWNER_NOTIFY_KEY_ORDER,
    PERSONAL_OWNER_NOTIFY_KEYS,
    TG_NOTIFY_EVENT_LABELS,
)
from app.services.node_manager import get_active_adapter
from app.services.vpn_profile_visibility import resolve_effective_visible_vpn_profiles

router = APIRouter()


def _mini_notify_settings_response(db: Session, user: User) -> AdminNotifySettingsResponse:
    response = _admin_notify_settings_response(db, user)
    if user.role == UserRole.admin:
        return response
    labels = dict(TG_NOTIFY_EVENT_LABELS)
    merged = user.merged_tg_notify_events()
    return AdminNotifySettingsResponse(
        telegram_id=response.telegram_id,
        recipient_user_ids=[],
        notify_enabled=response.notify_enabled,
        bot_token_set=response.bot_token_set,
        events=[
            AdminNotifyEventItem(
                key=key,
                label=labels.get(key, key),
                enabled=merged.get(key, False),
            )
            for key in PERSONAL_OWNER_NOTIFY_KEY_ORDER
        ],
        node_offline_grace_seconds=response.node_offline_grace_seconds,
    )


@router.get("/settings")
def mini_settings(db: Session = Depends(get_db), current_user: User = Depends(get_tg_mini_user)):
    from app.routers import tg_mini as root

    adapter = get_active_adapter(db)
    token = root._get_bot_token(db)
    is_admin = current_user.role == UserRole.admin
    policy = resolve_effective_visible_vpn_profiles(db, current_user)
    return {
        "server_ip": adapter.get_server_ip() if is_admin else "",
        "bot_configured": bool(token),
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role.value,
        "theme": current_user.theme,
        "visible_vpn_profiles": policy,
    }


@router.get("/visible-vpn-profiles", response_model=EffectiveVisibleVpnProfilesResponse)
def mini_visible_vpn_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_tg_mini_user),
):
    policy = resolve_effective_visible_vpn_profiles(db, current_user)
    return EffectiveVisibleVpnProfilesResponse(
        policy=VisibleVpnProfilesPolicy(**policy),
        inherited=True,
    )


@router.get("/admin-notify", response_model=AdminNotifySettingsResponse)
def mini_get_admin_notify(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_tg_mini_user),
):
    return _mini_notify_settings_response(db, current_user)


@router.patch("/admin-notify", response_model=AdminNotifySettingsResponse)
def mini_update_admin_notify(
    payload: AdminNotifySettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_tg_mini_user),
):
    from app.routers import tg_mini as root

    is_admin = current_user.role == UserRole.admin
    if payload.telegram_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Изменение Telegram ID в Mini App недоступно — используйте /link в боте или веб-панель",
        )
    if payload.recipient_user_ids is not None and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только администратор может менять получателей уведомлений",
        )
    if payload.events is not None:
        merged = current_user.merged_tg_notify_events()
        allowed_keys = DEFAULT_TG_NOTIFY_EVENTS if is_admin else PERSONAL_OWNER_NOTIFY_KEYS
        for key in allowed_keys:
            if key in payload.events:
                merged[key] = bool(payload.events[key])
        current_user.tg_notify_events = json.dumps(merged)
    if payload.recipient_user_ids is not None:
        from app.services.telegram_recipients import join_user_ids

        root._set_setting(db, "telegram_notify_recipient_user_ids", join_user_ids(payload.recipient_user_ids))
    if payload.node_offline_grace_seconds is not None:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только администратор может менять таймаут offline-уведомлений",
            )
        from app.services.node_status_notify import set_node_offline_grace_seconds

        set_node_offline_grace_seconds(db, payload.node_offline_grace_seconds)
    db.commit()
    db.refresh(current_user)
    return _mini_notify_settings_response(db, current_user)


@router.post("/admin-notify/test", response_model=MessageResponse)
def mini_test_admin_notify(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_tg_mini_user),
):
    from app.routers import tg_mini as root

    bot_token = root._get_bot_token(db)
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен бота не настроен")
    merged = current_user.merged_tg_notify_events()
    if current_user.role == UserRole.admin:
        enabled = [label for key, label in TG_NOTIFY_EVENT_LABELS if merged.get(key)]
    else:
        labels = dict(TG_NOTIFY_EVENT_LABELS)
        enabled = [labels[key] for key in PERSONAL_OWNER_NOTIFY_KEY_ORDER if merged.get(key)]
    events_text = "\n".join(f"  ✓ {item}" for item in enabled) if enabled else "  (нет включённых событий)"
    text = (
        "🔔 <b>Тест уведомлений AdminPanelAZ</b>\n\n"
        f"Аккаунт: <code>{current_user.username}</code>\n\n"
        f"Включённые события:\n{events_text}"
    )
    if current_user.role != UserRole.admin:
        if not current_user.telegram_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Привяжите Telegram через /link в боте",
            )
        from app.services.telegram import send_tg_message

        if not send_tg_message(bot_token, current_user.telegram_id, text, run_async=False):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось отправить сообщение в Telegram")
        return MessageResponse(message="Тестовое сообщение отправлено")
    sent, total = _send_test_message_to_recipients(db, current_user, text)
    return MessageResponse(message=f"Тестовое сообщение отправлено ({sent} из {total})")


@router.get("/telegram-settings", response_model=TelegramSettingsResponse)
def mini_get_telegram_settings(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_tg_mini_admin),
):
    return _telegram_settings_response(db, request)


@router.patch("/telegram-settings", response_model=TelegramSettingsResponse)
def mini_update_telegram_settings(
    payload: TelegramSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_tg_mini_admin),
):
    return update_telegram_settings(payload, request, db, admin)


@router.post("/telegram-settings/test", response_model=MessageResponse)
def mini_test_telegram(db: Session = Depends(get_db), _: User = Depends(require_tg_mini_admin)):
    from app.routers import tg_mini as root
    from app.services.telegram import send_tg_message
    from app.services.telegram_recipients import get_setting_chat_ids

    bot_token = root._get_bot_token(db)
    chat_ids = get_setting_chat_ids(lambda key, default="": root._get_setting(db, key, default))
    if not bot_token or not chat_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите токен бота и получателей бэкапов")
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


@router.post("/check-bot-delivery")
def check_bot_delivery(db: Session = Depends(get_db), _: User = Depends(require_tg_mini_admin)):
    from app.routers import tg_mini as root
    import httpx

    token = root._get_bot_token(db)
    if not token:
        return {"success": False, "message": "Бот не настроен"}
    try:
        resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            return {"success": True, "message": f"Бот @{data['result'].get('username', '')} доступен"}
        return {"success": False, "message": data.get("description", "Ошибка API")}
    except Exception as exc:
        return {"success": False, "message": str(exc)}
