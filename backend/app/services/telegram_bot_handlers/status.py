from __future__ import annotations

from app.services.telegram_api import send_message
from app.services.telegram_bot_data import build_dashboard_summary
from app.services.telegram_bot_handlers.base import BotContext, unlinked_message
from app.services import telegram_bot_i18n as i18n


async def handle_status(ctx: BotContext) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    summary = build_dashboard_summary(ctx.db, ctx.user)
    text = i18n.STATUS_BODY.format(
        title=i18n.STATUS_TITLE,
        total_configs=summary["total_configs"],
        connected_openvpn=summary["connected_openvpn"],
        connected_wireguard=summary["connected_wireguard"],
        server_ip=summary["server_ip"],
        timestamp=summary["timestamp"],
    )
    await send_message(ctx.bot_token, ctx.chat_id, text)
