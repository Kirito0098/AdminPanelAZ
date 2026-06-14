from __future__ import annotations

from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard
from app.services import telegram_bot_i18n as i18n


async def handle_start(ctx: BotContext) -> None:
    if ctx.user is None:
        text = i18n.START_UNLINKED.format(title=i18n.START_TITLE)
        await send_message(ctx.bot_token, ctx.chat_id, text)
        return

    rows = []
    if ctx.mini_app_url:
        rows.append([inline_button(i18n.BTN_OPEN_MINI_APP, url=ctx.mini_app_url)])
    rows.append([inline_button(i18n.BTN_HELP, callback_data="help")])
    text = i18n.START_LINKED.format(
        title=i18n.START_TITLE,
        username=ctx.user.username,
        role=ctx.user.role.value,
    )
    await send_message(ctx.bot_token, ctx.chat_id, text, reply_markup=inline_keyboard(rows))
