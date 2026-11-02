"""Режим переписки абонента с администратором (модуль user_messaging)."""

from __future__ import annotations

from app.services import telegram_bot_i18n as i18n
from app.services import user_messages as chat_service
from app.services.feature_guards import get_feature_service
from app.services.telegram_api import edit_message_reply_markup, send_message, send_message_result
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard
from app.services.telegram_bot_handlers.menu import build_reply_keyboard
from app.models import User, UserRole
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
    if ctx.user.role == UserRole.admin:
        # Админ отвечает из панели; режим переписки ему не нужен.
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CHAT_ADMIN_HINT)
        return
    chat_service.enter_chat_mode(ctx.db, ctx.user)
    sent = await send_message_result(
        ctx.bot_token, ctx.chat_id, i18n.CHAT_ENTER, reply_markup=build_reply_keyboard(ctx)
    )
    # Reply-клавиатуру в Telegram можно свернуть (кнопка-иконка у поля ввода) — тогда
    # «Завершить» не видно. Дублируем её inline-кнопкой в самом сообщении.
    message_id = (sent or {}).get("message_id")
    if isinstance(message_id, int):
        await edit_message_reply_markup(
            ctx.bot_token,
            ctx.chat_id,
            message_id,
            reply_markup=inline_keyboard(
                [[inline_button(i18n.BTN_CHAT_STOP, callback_data="nav:chat_stop")]]
            ),
        )


async def handle_chat_stop(ctx: BotContext) -> None:
    """Выход из режима переписки."""
    if ctx.user is not None:
        chat_service.leave_chat_mode(ctx.db, ctx.user)
    await send_message(
        ctx.bot_token, ctx.chat_id, i18n.CHAT_STOPPED, reply_markup=build_reply_keyboard(ctx)
    )


async def handle_admin_card_reply(ctx: BotContext, message: dict) -> bool:
    """Ответ админа реплаем на карточку «новое сообщение» → абоненту."""
    if ctx.user is None or ctx.user.role != UserRole.admin:
        return False
    if not chat_available():
        return False
    reply = message.get("reply_to_message") or {}
    reply_id = reply.get("message_id")
    if not isinstance(reply_id, int):
        return False
    card = chat_service.find_card(
        ctx.db, admin_chat_id=str(ctx.chat_id), message_id=reply_id
    )
    if card is None:
        return False
    target = ctx.db.get(User, card.user_id)
    if target is None:
        return False
    text = (message.get("text") or "").strip()
    if not text:
        return False
    limit = chat_service.MESSAGE_MAX_LEN - len(chat_service.REPLY_PREFIX) - 1
    if len(text) > limit:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CHAT_TOO_LONG)
        return True
    _, delivered, warning = chat_service.send_admin_reply(
        ctx.db, user=target, admin=ctx.user, text=text
    )
    confirm = (
        f"Отправлено абоненту {target.username}."
        if delivered
        else f"Сохранено, но не доставлено: {warning}"
    )
    await send_message(ctx.bot_token, ctx.chat_id, confirm)
    return True


async def handle_chat_text(ctx: BotContext, message: dict) -> bool:
    """Текст в режиме переписки → в чат админу.

    ``False`` — режим выключен или сообщение пустое: пусть решает обычная
    маршрутизация (меню, коды, «не понял»).
    """
    if ctx.user is None or ctx.user.role == UserRole.admin:
        return False
    if not chat_service.in_chat_mode(ctx.user):
        return False
    text = (message.get("text") or "").strip()
    if not text:
        # Фото, файлы, стикеры и прочие вложения в переписке не принимаем:
        # чек идёт через «Оплатить (чек)».
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CHAT_TEXT_ONLY)
        return True
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
    await notify_admins_new_message(
        ctx.db, user=ctx.user, message=stored, first_in_thread=first_in_thread
    )
    await send_message(ctx.bot_token, ctx.chat_id, i18n.CHAT_SENT)
    return True
