"""Режим переписки абонента с администратором (модуль user_messaging)."""

from __future__ import annotations

from app.services import telegram_bot_i18n as i18n
from app.services import user_messages as chat_service
from app.services.feature_guards import get_feature_service
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext
from app.services.telegram_bot_handlers.menu import build_reply_keyboard
from app.services.user_message_notify import notify_admins_new_message


def chat_available() -> bool:
    return get_feature_service().is_enabled("user_messaging")


async def handle_admin_chat(ctx: BotContext) -> None:
    """Вход в режим переписки: запоминаем время входа и просим написать."""
    if not chat_available():
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CHAT_DISABLED)
        return
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CHAT_NEED_LINK)
        return
    chat_service.enter_chat_mode(ctx.db, ctx.user)
    await send_message(
        ctx.bot_token, ctx.chat_id, i18n.CHAT_ENTER, reply_markup=build_reply_keyboard(ctx)
    )


async def handle_chat_stop(ctx: BotContext) -> None:
    """Выход из режима переписки."""
    if ctx.user is not None:
        chat_service.leave_chat_mode(ctx.db, ctx.user)
    await send_message(
        ctx.bot_token, ctx.chat_id, i18n.CHAT_STOPPED, reply_markup=build_reply_keyboard(ctx)
    )


async def handle_chat_text(ctx: BotContext, message: dict) -> bool:
    """Текст в режиме переписки → в чат админу.

    ``False`` — режим выключен или сообщение пустое: пусть решает обычная
    маршрутизация (меню, коды, «не понял»).
    """
    if ctx.user is None or not chat_service.in_chat_mode(ctx.user):
        return False
    text = (message.get("text") or "").strip()
    if not text:
        return False
    if len(text) > chat_service.MESSAGE_MAX_LEN:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CHAT_TOO_LONG)
        return True
    raw_id = message.get("message_id")
    stored = chat_service.record_inbound(
        ctx.db,
        user=ctx.user,
        text=text,
        telegram_message_id=raw_id if isinstance(raw_id, int) else None,
    )
    if stored is None:
        # Повторная доставка того же апдейта: молчим, чтобы не дублировать ответ.
        return True
    first_in_thread = chat_service.unread_for_user(ctx.db, user_id=ctx.user.id) == 1
    notify_admins_new_message(
        ctx.db, user=ctx.user, message=stored, first_in_thread=first_in_thread
    )
    await send_message(ctx.bot_token, ctx.chat_id, i18n.CHAT_SENT)
    return True
