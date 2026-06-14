"""Telegram bot /settings menu — Phase 3 settings from panel."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from starlette.requests import Request

from app.schemas import TelegramSettingsUpdate
from app.services.action_log import log_action
from app.services.telegram_api import edit_message_text, send_message
from app.services.telegram_bot_handlers.base import (
    BotContext,
    inline_button,
    inline_keyboard,
    is_admin,
    unlinked_message,
)
from app.services.telegram_bot_handlers import settings_fsm
from app.services import telegram_bot_i18n as i18n

_SECTION_LABELS: dict[str, str] = i18n.SETTINGS_SECTION_LABELS


def _make_bot_request(ctx: BotContext) -> Request:
    from urllib.parse import urlparse

    url_root = (ctx.mini_app_url or "").removesuffix("/api/tg-mini").rstrip("/")
    if not url_root:
        url_root = "https://localhost"
    parsed = urlparse(url_root)
    scheme = parsed.scheme or "https"
    host = parsed.netloc or "localhost"
    hostname = parsed.hostname or "localhost"
    port = parsed.port or (443 if scheme == "https" else 80)
    headers = [
        (b"host", host.encode()),
        (b"x-forwarded-proto", scheme.encode()),
        (b"x-forwarded-host", host.encode()),
    ]
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/api/settings/telegram",
        "headers": headers,
        "scheme": scheme,
        "server": (hostname, port),
        "client": ("127.0.0.1", 0),
    }
    return Request(scope)


def _remote_addr(ctx: BotContext) -> str:
    return f"telegram:{ctx.telegram_user_id}"


def _log_bot_action(ctx: BotContext, action: str, details: str) -> None:
    if ctx.user is None:
        return
    if not details.startswith("source=telegram_bot"):
        details = f"source=telegram_bot; {details}"
    log_action(
        ctx.db,
        action=action,
        user_id=ctx.user.id,
        username=ctx.user.username,
        details=details,
        remote_addr=_remote_addr(ctx),
    )


def _get_telegram_settings(ctx: BotContext):
    from app.routers.maintenance import _telegram_settings_response

    return _telegram_settings_response(ctx.db, _make_bot_request(ctx))


def _apply_telegram_patch(
    ctx: BotContext,
    payload: TelegramSettingsUpdate,
    *,
    log_action_name: str = "settings_telegram_update",
    log_details: str,
) -> Any:
    from app.routers.maintenance import update_telegram_settings

    try:
        result = update_telegram_settings(payload, _make_bot_request(ctx), ctx.db, ctx.user)
        _log_bot_action(ctx, log_action_name, log_details)
        return result
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        raise ValueError(detail) from exc


def _on_off(value: bool) -> str:
    return i18n.on_off(value)


def _yes_no(value: bool) -> str:
    return i18n.yes_no(value)


def _format_telegram_menu(settings) -> str:
    username = settings.bot_username or i18n.TG_USERNAME_DEFAULT
    if username and not username.startswith("@"):
        username = f"@{username}"
    chat = settings.chat_id or i18n.TG_CHAT_DEFAULT
    return i18n.TG_SETTINGS_BODY.format(
        title=i18n.TG_SETTINGS_TITLE,
        token_icon=_yes_no(settings.bot_token_set),
        token_state=i18n.token_set(settings.bot_token_set),
        username=username,
        max_age=settings.auth_max_age_seconds,
        chat_id=chat,
        notify=_on_off(settings.notify_enabled),
        notify_backup=_on_off(settings.notify_on_backup),
        interactive=_on_off(settings.interactive_enabled),
        webhook_icon=_yes_no(settings.webhook_registered),
        webhook_state=i18n.webhook_registered(settings.webhook_registered),
        mini_app_url=settings.mini_app_url,
    )


def _telegram_keyboard(settings) -> dict:
    ne = settings.notify_enabled
    nb = settings.notify_on_backup
    ie = settings.interactive_enabled
    token_ok = settings.bot_token_set
    rows = [
        [
            inline_button(
                f"🔔 Уведомления: {_on_off(ne)}",
                callback_data=f"st:tg:ne:{0 if ne else 1}",
            )
        ],
        [
            inline_button(
                f"📦 TG при бэкапе: {_on_off(nb)}",
                callback_data=f"st:tg:nb:{0 if nb else 1}",
            )
        ],
        [
            inline_button(
                f"🤖 Интерактив: {_on_off(ie)}",
                callback_data="st:tg:ie:1" if not ie else "st:tg:cfrm:ie:0",
            )
        ],
        [
            inline_button("✏️ Username", callback_data="st:tg:ask:user"),
            inline_button("✏️ Chat ID", callback_data="st:tg:ask:chat"),
        ],
        [
            inline_button("✏️ Max auth age", callback_data="st:tg:ask:age"),
            inline_button("🔑 Сменить токен", callback_data="st:tg:ask:token"),
        ],
    ]
    action_row: list = []
    if token_ok and settings.chat_id:
        action_row.append(inline_button("📤 Тест chat_id", callback_data="st:tg:test"))
    if ie and token_ok:
        action_row.append(inline_button("🔗 Webhook", callback_data="st:tg:wh:reg"))
    if settings.webhook_registered:
        action_row.append(inline_button("🗑 Webhook", callback_data="st:tg:cfrm:wh:del"))
    if action_row:
        rows.append(action_row)
    rows.extend(
        [
            [inline_button("🔄 Обновить", callback_data="st:tg")],
            [inline_button("◀️ Настройки", callback_data="st:root")],
        ]
    )
    return inline_keyboard(rows)


def _settings_root_keyboard() -> dict:
    return inline_keyboard(
        [
            [
                inline_button(i18n.BTN_SETTINGS_TELEGRAM, callback_data="st:tg"),
                inline_button(i18n.BTN_SETTINGS_NOTIFY, callback_data="st:an"),
            ],
            [
                inline_button(i18n.BTN_SETTINGS_BACKUPS, callback_data="st:bk"),
                inline_button(i18n.BTN_SETTINGS_MONITOR, callback_data="st:mon"),
            ],
            [
                inline_button(i18n.BTN_SETTINGS_SECURITY, callback_data="st:sec"),
                inline_button(i18n.BTN_SETTINGS_MAINTENANCE, callback_data="st:mnt"),
            ],
            [inline_button(i18n.BTN_BACK, callback_data="st:back")],
        ]
    )


def _settings_root_text() -> str:
    return i18n.SETTINGS_ROOT_TITLE


async def _send_or_edit(
    ctx: BotContext,
    text: str,
    *,
    markup: dict | None = None,
    message_id: int | None = None,
) -> None:
    if message_id is not None:
        await edit_message_text(ctx.bot_token, ctx.chat_id, message_id, text, reply_markup=markup)
    else:
        await send_message(ctx.bot_token, ctx.chat_id, text, reply_markup=markup)


async def _require_admin_ctx(ctx: BotContext) -> bool:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return False
    if not is_admin(ctx.user):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return False
    return True


async def handle_settings_root(ctx: BotContext, *, message_id: int | None = None) -> None:
    if not await _require_admin_ctx(ctx):
        return
    settings_fsm.clear_pending(ctx.telegram_user_id)
    await _send_or_edit(
        ctx,
        _settings_root_text(),
        markup=_settings_root_keyboard(),
        message_id=message_id,
    )


async def handle_settings_telegram(ctx: BotContext, *, message_id: int | None = None) -> None:
    if not await _require_admin_ctx(ctx):
        return
    settings = _get_telegram_settings(ctx)
    await _send_or_edit(
        ctx,
        _format_telegram_menu(settings),
        markup=_telegram_keyboard(settings),
        message_id=message_id,
    )


async def handle_settings_stub(ctx: BotContext, section: str, *, message_id: int | None = None) -> None:
    if not await _require_admin_ctx(ctx):
        return
    label = _SECTION_LABELS.get(section, section)
    text = f"📋 <b>{label}</b>\n\nРаздел будет доступен в следующем обновлении."
    markup = inline_keyboard([[inline_button("◀️ Настройки", callback_data="st:root")]])
    await _send_or_edit(ctx, text, markup=markup, message_id=message_id)


async def _ask_text_input(ctx: BotContext, field: settings_fsm.FieldKind, prompt: str) -> None:
    settings_fsm.set_pending(ctx.telegram_user_id, field)
    await send_message(
        ctx.bot_token,
        ctx.chat_id,
        prompt,
        reply_markup={"force_reply": True, "selective": True},
    )


async def handle_settings_callback(ctx: BotContext, data: str, *, message_id: int | None) -> None:
    if data == "st:back":
        from app.services.telegram_bot_handlers.start import handle_start

        settings_fsm.clear_pending(ctx.telegram_user_id)
        await handle_start(ctx)
        return

    if data == "st:root":
        await handle_settings_root(ctx, message_id=message_id)
        return

    if data == "st:tg":
        await handle_settings_telegram(ctx, message_id=message_id)
        return

    if data == "st:an" or data.startswith("st:an:"):
        from app.services.telegram_bot_handlers.settings_admin_notify import handle_admin_notify_callback

        await handle_admin_notify_callback(ctx, data, message_id=message_id)
        return

    if data == "st:mon" or data.startswith("st:mon:"):
        from app.services.telegram_bot_handlers.settings_monitor import handle_monitor_callback

        await handle_monitor_callback(ctx, data, message_id=message_id)
        return

    if data == "st:bk" or data.startswith("st:bk:"):
        from app.services.telegram_bot_handlers.settings_backups import handle_backups_callback

        await handle_backups_callback(ctx, data, message_id=message_id)
        return

    if data == "st:mnt" or data.startswith("st:mnt:"):
        from app.services.telegram_bot_handlers.settings_maintenance import handle_maintenance_callback

        await handle_maintenance_callback(ctx, data, message_id=message_id)
        return

    if data == "st:sec" or data.startswith("st:sec:"):
        from app.services.telegram_bot_handlers.settings_security import handle_security_callback

        await handle_security_callback(ctx, data, message_id=message_id)
        return

    if not data.startswith("st:tg:"):
        return

    if not await _require_admin_ctx(ctx):
        return

    rest = data[len("st:tg:") :]

    try:
        if rest.startswith("ne:"):
            enabled = rest.endswith(":1")
            _apply_telegram_patch(
                ctx,
                TelegramSettingsUpdate(notify_enabled=enabled),
                log_details=f"field=notify_enabled; value={enabled}",
            )
            await handle_settings_telegram(ctx, message_id=message_id)
            return

        if rest.startswith("nb:"):
            enabled = rest.endswith(":1")
            _apply_telegram_patch(
                ctx,
                TelegramSettingsUpdate(notify_on_backup=enabled),
                log_details=f"field=notify_on_backup; value={enabled}",
            )
            await handle_settings_telegram(ctx, message_id=message_id)
            return

        if rest == "ie:1":
            _apply_telegram_patch(
                ctx,
                TelegramSettingsUpdate(interactive_enabled=True),
                log_details="field=interactive_enabled; value=true",
            )
            await handle_settings_telegram(ctx, message_id=message_id)
            return

        if rest == "cfrm:ie:0":
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Да", callback_data="st:tg:do:ie:0"),
                        inline_button("❌ Отмена", callback_data="st:tg"),
                    ]
                ]
            )
            await _send_or_edit(
                ctx,
                "⚠️ Выключить интерактивный бот?\nWebhook будет удалён.",
                markup=markup,
                message_id=message_id,
            )
            return

        if rest == "do:ie:0":
            _apply_telegram_patch(
                ctx,
                TelegramSettingsUpdate(interactive_enabled=False),
                log_details="field=interactive_enabled; value=false",
            )
            await handle_settings_telegram(ctx, message_id=message_id)
            return

        if rest == "ask:user":
            await _ask_text_input(ctx, "user", i18n.TG_ASK_USERNAME)
            return

        if rest == "ask:chat":
            await _ask_text_input(ctx, "chat", i18n.TG_ASK_CHAT)
            return

        if rest == "ask:age":
            await _ask_text_input(ctx, "age", i18n.TG_ASK_AGE)
            return

        if rest == "ask:token":
            await _ask_text_input(ctx, "token", i18n.TG_ASK_TOKEN)
            return

        if rest == "cfrm:token":
            pending = settings_fsm.get_pending(ctx.telegram_user_id)
            if not pending or pending.field != "token" or not pending.value:
                await send_message(ctx.bot_token, ctx.chat_id, i18n.TG_NO_PENDING_TOKEN)
                return
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Да", callback_data="st:tg:do:token"),
                        inline_button("❌ Отмена", callback_data="st:tg"),
                    ]
                ]
            )
            await _send_or_edit(
                ctx,
                "⚠️ Заменить токен бота?\nСтарый перестанет работать.",
                markup=markup,
                message_id=message_id,
            )
            return

        if rest == "do:token":
            pending = settings_fsm.get_pending(ctx.telegram_user_id)
            if not pending or pending.field != "token" or not pending.value:
                await send_message(ctx.bot_token, ctx.chat_id, i18n.TG_NO_PENDING_TOKEN_SHORT)
                return
            token = pending.value
            settings_fsm.clear_pending(ctx.telegram_user_id)
            _apply_telegram_patch(
                ctx,
                TelegramSettingsUpdate(bot_token=token),
                log_action_name="settings_telegram_token",
                log_details="action=token_change",
            )
            await send_message(ctx.bot_token, ctx.chat_id, "✅ Токен бота обновлён.")
            await handle_settings_telegram(ctx)
            return

        if rest == "test":
            from app.routers.maintenance import test_telegram

            test_telegram(ctx.db, ctx.user)
            _log_bot_action(ctx, "settings_telegram_test", "action=test")
            await send_message(ctx.bot_token, ctx.chat_id, "✅ Тестовое сообщение отправлено в chat_id.")
            return

        if rest == "wh:reg":
            from app.routers.maintenance import register_telegram_webhook

            register_telegram_webhook(_make_bot_request(ctx), ctx.db, ctx.user)
            _log_bot_action(ctx, "settings_telegram_webhook", "action=register")
            await send_message(ctx.bot_token, ctx.chat_id, "✅ Webhook зарегистрирован.")
            await handle_settings_telegram(ctx, message_id=message_id)
            return

        if rest == "cfrm:wh:del":
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Да", callback_data="st:tg:do:wh:del"),
                        inline_button("❌ Отмена", callback_data="st:tg"),
                    ]
                ]
            )
            await _send_or_edit(
                ctx,
                "⚠️ Удалить webhook?\nБот перестанет принимать команды.",
                markup=markup,
                message_id=message_id,
            )
            return

        if rest == "do:wh:del":
            from app.routers.maintenance import unregister_telegram_webhook

            unregister_telegram_webhook(_make_bot_request(ctx), ctx.db, ctx.user)
            _log_bot_action(ctx, "settings_telegram_webhook", "action=delete")
            await send_message(ctx.bot_token, ctx.chat_id, "✅ Webhook удалён.")
            await handle_settings_telegram(ctx, message_id=message_id)
            return

    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
        return
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {detail}")
        return


async def handle_settings_text(ctx: BotContext, text: str) -> bool:
    """Process FSM text input. Returns True if consumed."""
    from app.services.telegram_bot_handlers.settings_admin_notify import handle_admin_notify_text
    from app.services.telegram_bot_handlers.settings_monitor import handle_monitor_text
    from app.services.telegram_bot_handlers.settings_backups import handle_backups_text
    from app.services.telegram_bot_handlers.settings_security import handle_security_text

    if await handle_admin_notify_text(ctx, text):
        return True
    if await handle_monitor_text(ctx, text):
        return True
    if await handle_backups_text(ctx, text):
        return True
    if await handle_security_text(ctx, text):
        return True

    pending = settings_fsm.get_pending(ctx.telegram_user_id)
    if pending is None:
        return False
    if not await _require_admin_ctx(ctx):
        settings_fsm.clear_pending(ctx.telegram_user_id)
        return True

    raw = (text or "").strip()
    if not raw:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.VALUE_EMPTY)
        return True

    try:
        if pending.field == "token":
            settings_fsm.set_pending_value(ctx.telegram_user_id, raw)
            markup = inline_keyboard(
                [
                    [
                        inline_button("✅ Подтвердить", callback_data="st:tg:cfrm:token"),
                        inline_button("❌ Отмена", callback_data="st:tg"),
                    ]
                ]
            )
            await send_message(
                ctx.bot_token,
                ctx.chat_id,
                "⚠️ Заменить токен бота?\nСтарый перестанет работать.",
                reply_markup=markup,
            )
            return True

        if pending.field == "user":
            settings_fsm.clear_pending(ctx.telegram_user_id)
            _apply_telegram_patch(
                ctx,
                TelegramSettingsUpdate(bot_username=raw),
                log_details=f"field=bot_username; value={raw.lstrip('@')}",
            )
            await send_message(ctx.bot_token, ctx.chat_id, "✅ Username сохранён.")
            await handle_settings_telegram(ctx)
            return True

        if pending.field == "chat":
            settings_fsm.clear_pending(ctx.telegram_user_id)
            _apply_telegram_patch(
                ctx,
                TelegramSettingsUpdate(chat_id=raw),
                log_details=f"field=chat_id; value={raw}",
            )
            await send_message(ctx.bot_token, ctx.chat_id, "✅ Chat ID сохранён.")
            await handle_settings_telegram(ctx)
            return True

        if pending.field == "age":
            if not raw.isdigit():
                await send_message(ctx.bot_token, ctx.chat_id, i18n.TG_AGE_INVALID)
                return True
            age = int(raw)
            if age < 30 or age > 86400:
                await send_message(ctx.bot_token, ctx.chat_id, i18n.TG_AGE_RANGE)
                return True
            settings_fsm.clear_pending(ctx.telegram_user_id)
            _apply_telegram_patch(
                ctx,
                TelegramSettingsUpdate(auth_max_age_seconds=age),
                log_details=f"field=auth_max_age_seconds; value={age}",
            )
            await send_message(ctx.bot_token, ctx.chat_id, f"✅ Max auth age: {age} сек.")
            await handle_settings_telegram(ctx)
            return True

    except ValueError as exc:
        await send_message(ctx.bot_token, ctx.chat_id, f"❌ {exc}")
        return True

    return True
