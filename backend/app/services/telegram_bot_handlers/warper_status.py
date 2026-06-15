"""Telegram bot /warper — AZ-WARP status (Phase 4, admin, if warper enabled)."""

from __future__ import annotations

from app.services.feature_guards import get_feature_service
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.tg_mini_status import build_cidr_status_payload, build_warper_status_payload
from app.services.telegram_bot_handlers.base import BotContext, is_admin, unlinked_message
from app.services.telegram_bot_handlers.ui import nav_footer_keyboard, send_or_edit
from app.services import telegram_bot_i18n as i18n


async def handle_warper_status(ctx: BotContext, *, message_id: int | None = None) -> None:
    if ctx.user is None:
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not is_admin(ctx.user):
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return
    if not get_feature_service().is_enabled("warper"):
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.WARPER_DISABLED)
        return

    try:
        payload = build_warper_status_payload(ctx.db)
        text = i18n.WARPER_BODY.format(
            title=i18n.WARPER_TITLE,
            node_name=payload["node_name"],
            node_host=payload["node_host"],
            status=payload["status"],
        )
    except Exception as exc:
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.WARPER_ERROR.format(detail=exc))
        return

    markup = nav_footer_keyboard(refresh="nav:warper")
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)
