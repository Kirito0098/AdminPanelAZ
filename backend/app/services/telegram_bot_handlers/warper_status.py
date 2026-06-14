"""Telegram bot /warper — AZ-WARP status (Phase 4, admin, if warper enabled)."""

from __future__ import annotations

from app.services.feature_guards import get_feature_service
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, is_admin, unlinked_message
from app.services import telegram_bot_i18n as i18n


async def handle_warper_status(ctx: BotContext) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not is_admin(ctx.user):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return
    if not get_feature_service().is_enabled("warper"):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.WARPER_DISABLED)
        return

    try:
        node = get_active_node(ctx.db)
        adapter = get_active_adapter(ctx.db)
        raw_status = adapter.get_warper_status()
        if isinstance(raw_status, dict):
            status_text = raw_status.get("status") or raw_status.get("mode") or str(raw_status)
        else:
            status_text = str(raw_status)
        text = i18n.WARPER_BODY.format(
            title=i18n.WARPER_TITLE,
            node_name=node.name,
            node_host=node.host,
            status=status_text,
        )
    except Exception as exc:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.WARPER_ERROR.format(detail=exc))
        return

    await send_message(ctx.bot_token, ctx.chat_id, text)
