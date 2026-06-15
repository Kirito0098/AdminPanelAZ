from __future__ import annotations

from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext
from app.services.telegram_bot_handlers.menu import build_main_inline_menu, build_reply_keyboard
from app.services.telegram_bot_handlers.ui import INVISIBLE_TEXT, role_label
from app.services import telegram_bot_i18n as i18n


async def handle_start(ctx: BotContext) -> None:
    if ctx.user is None:
        text = i18n.START_UNLINKED.format(title=i18n.START_TITLE)
        await send_message(
            ctx.bot_token,
            ctx.chat_id,
            text,
            reply_markup=build_reply_keyboard(ctx),
        )
        return

    text = i18n.START_LINKED.format(
        title=i18n.START_TITLE,
        username=ctx.user.username,
        role=role_label(ctx.user.role.value),
    )
    await send_message(
        ctx.bot_token,
        ctx.chat_id,
        text,
        reply_markup=build_main_inline_menu(ctx),
    )
    await send_message(
        ctx.bot_token,
        ctx.chat_id,
        INVISIBLE_TEXT,
        reply_markup=build_reply_keyboard(ctx),
    )
