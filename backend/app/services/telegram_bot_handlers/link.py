from __future__ import annotations

from fastapi import HTTPException

from app.services.action_log import log_action
from app.services.auth_rate_limit import auth_rate_limit_service
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext
from app.services.telegram_link import redeem_link_code

_LINK_LOCKED = "Слишком много попыток привязки. Повторите позже."


async def handle_link(ctx: BotContext, code: str) -> None:
    key = f"telegram_link:{ctx.telegram_user_id}"
    try:
        auth_rate_limit_service.check(key, detail=_LINK_LOCKED)
    except HTTPException as exc:
        await send_message(ctx.bot_token, ctx.chat_id, exc.detail)
        return
    ok, message, user = redeem_link_code(ctx.db, code, ctx.telegram_user_id)
    if ok:
        auth_rate_limit_service.record_success(key)
    else:
        auth_rate_limit_service.record_failure(key)
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
