from __future__ import annotations

from html import escape

from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext
from app.services.telegram_bot_handlers.menu import build_reply_keyboard
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers.ui import role_label
from app.services import telegram_bot_i18n as i18n
from app.services.user_access_requests import _accept_requests


def _start_role_display(role: str | None) -> str:
    value = (role or "").strip().lower()
    return i18n.START_ROLE_DISPLAY.get(value, f"🔑 {role_label(value)}")


async def handle_start(ctx: BotContext, *, payload: str | None = None) -> None:
    settings_fsm.clear_pending(ctx.telegram_user_id)
    if payload == "chat":
        from app.services.telegram_bot_handlers.chat import handle_admin_chat

        await handle_admin_chat(ctx)
        return
    if payload == "pay":
        from app.services.telegram_bot_handlers.access_requests import handle_pay_request

        await handle_pay_request(ctx)
        return
    if ctx.user is not None:
        from app.services.user_messages import leave_chat_mode

        leave_chat_mode(ctx.db, ctx.user)
    from app.services.telegram_widgets import send_hub

    if await send_hub(
        ctx.db,
        bot_token=ctx.bot_token,
        chat_id=ctx.chat_id,
        telegram_id=ctx.telegram_user_id,
        reply_markup=build_reply_keyboard(ctx),
    ):
        return
    if ctx.user is None:
        template = (
            i18n.START_UNLINKED_WITH_REQUESTS
            if _accept_requests(ctx.db)
            else i18n.START_UNLINKED
        )
        text = template.format(title=i18n.START_TITLE)
        await send_message(
            ctx.bot_token,
            ctx.chat_id,
            text,
            reply_markup=build_reply_keyboard(ctx),
        )
        return

    text = i18n.START_LINKED.format(
        title=i18n.START_TITLE,
        username=escape(ctx.user.username),
        role_display=_start_role_display(ctx.user.role.value),
    )
    await send_message(
        ctx.bot_token,
        ctx.chat_id,
        text,
        reply_markup=build_reply_keyboard(ctx),
    )
