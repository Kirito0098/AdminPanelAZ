from __future__ import annotations

from app.services.action_log import log_action
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext
from app.services.telegram_link import redeem_link_code


async def handle_link(ctx: BotContext, code: str) -> None:
    ok, message, user = redeem_link_code(ctx.db, code, ctx.telegram_user_id)
    await send_message(ctx.bot_token, ctx.chat_id, message)
    if ok and user:
        log_action(
            ctx.db,
            action="telegram_link",
            user_id=user.id,
            username=user.username,
            details=f"telegram_id={ctx.telegram_user_id}",
        )
        ctx.user = user
        from app.services.telegram_bot_handlers.start import handle_start

        await handle_start(ctx)
