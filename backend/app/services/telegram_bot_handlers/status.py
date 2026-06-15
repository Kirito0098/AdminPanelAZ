from __future__ import annotations

from app.services.telegram_bot_data import build_dashboard_summary
from app.services.telegram_bot_handlers.base import BotContext, inline_button, unlinked_message
from app.services.telegram_bot_handlers.ui import format_bot_timestamp, nav_footer_keyboard, send_or_edit
from app.services import telegram_bot_i18n as i18n


async def handle_status(ctx: BotContext, *, message_id: int | None = None) -> None:
    if ctx.user is None:
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    summary = build_dashboard_summary(ctx.db, ctx.user)
    text = i18n.STATUS_BODY.format(
        title=i18n.STATUS_TITLE,
        total_configs=summary["total_configs"],
        connected_openvpn=summary["connected_openvpn"],
        connected_wireguard=summary["connected_wireguard"],
        server_ip=summary["server_ip"],
        timestamp=format_bot_timestamp(summary["timestamp"]),
    )
    markup = nav_footer_keyboard(
        refresh="nav:status",
        extra_rows=[[inline_button(i18n.BTN_MENU_CONFIGS, callback_data="nav:configs")]],
    )
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)
