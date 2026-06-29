from __future__ import annotations

from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext
from app.services.telegram_bot_handlers.menu import build_reply_keyboard
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers.ui import role_label
from app.services import telegram_bot_i18n as i18n


def _start_role_display(role: str | None) -> str:
    value = (role or "").strip().lower()
    return i18n.START_ROLE_DISPLAY.get(value, f"🔑 {role_label(value)}")


async def handle_start(ctx: BotContext) -> None:
    settings_fsm.clear_pending(ctx.telegram_user_id)
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
        role_display=_start_role_display(ctx.user.role.value),
    )
    await send_message(
        ctx.bot_token,
        ctx.chat_id,
        text,
        reply_markup=build_reply_keyboard(ctx),
    )
