"""Telegram bot /cidr — CIDR pipeline status (Phase 4, admin)."""

from __future__ import annotations

from app.services.tg_mini_status import build_cidr_status_payload
from app.services.telegram_bot_handlers.base import BotContext, is_admin, unlinked_message
from app.services.telegram_bot_handlers.ui import nav_footer_keyboard, send_or_edit
from app.services import telegram_bot_i18n as i18n


def _format_cidr_status(db) -> str:
    data = build_cidr_status_payload(db)
    return i18n.CIDR_BODY.format(
        title=i18n.CIDR_TITLE,
        total=data["total_cidrs"],
        last_status=data.get("last_refresh_status") or i18n.CIDR_NONE,
        last_finished=data.get("last_refresh_finished") or i18n.CIDR_NONE,
        active_task=data.get("active_task") or i18n.CIDR_NONE,
        last_compile=str(
            (data.get("last_compile") or {}).get("finished_at")
            or (data.get("last_compile") or {}).get("started_at")
            or i18n.CIDR_NONE
        ),
        last_deploy=str(
            (data.get("last_deploy") or {}).get("status")
            or (data.get("last_deploy") or {}).get("finished_at")
            or i18n.CIDR_NONE
        ),
    )


async def handle_cidr_status(ctx: BotContext, *, message_id: int | None = None) -> None:
    if ctx.user is None:
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not is_admin(ctx.user):
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return

    try:
        text = _format_cidr_status(ctx.db)
    except Exception as exc:
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.CIDR_ERROR.format(detail=exc))
        return

    markup = nav_footer_keyboard(refresh="nav:cidr")
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)
