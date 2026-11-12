"""Telegram bot: ссылка клиентского портала для абонента."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.services import telegram_bot_i18n as i18n
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import BotContext, unlinked_message


def _fallback_link(ctx: BotContext) -> tuple[str | None, str | None]:
    """Создать/получить ссылку для текстового фолбэка. (url, error)."""
    from app.services.client_portal import (
        _active_user_token,
        get_or_create_user_portal_token,
        portal_page_url,
        rotate_user_portal_token,
    )
    from app.services.portal_link_settings import (
        get_portal_link_ttl_days,
        portal_link_expires_at,
    )

    ttl_days = get_portal_link_ttl_days(ctx.db)
    row = _active_user_token(ctx.db, user_id=ctx.user.id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires = (
        portal_link_expires_at(row.created_at, ttl_days) if row is not None else None
    )
    if row is not None and expires is not None and now >= expires:
        row = rotate_user_portal_token(ctx.db, user_id=ctx.user.id)
    elif row is None:
        row = get_or_create_user_portal_token(ctx.db, user_id=ctx.user.id)
    try:
        return portal_page_url(ctx.db, row.token), None
    except HTTPException as exc:
        return None, str(exc.detail)


async def handle_portal(ctx: BotContext) -> None:
    """Показать карточку портала; если виджеты недоступны — текстом."""
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not get_feature_service().is_enabled("client_portal"):
        await send_message(
            ctx.bot_token, ctx.chat_id, module_disabled_message("client_portal")
        )
        return

    from app.services.telegram_widgets import send_portal_card

    if await send_portal_card(
        ctx.db,
        bot_token=ctx.bot_token,
        chat_id=ctx.chat_id,
        telegram_id=ctx.telegram_user_id,
        user=ctx.user,
    ):
        return

    url, error = _fallback_link(ctx)
    if url is None:
        await send_message(ctx.bot_token, ctx.chat_id, error or i18n.UNLINKED)
        return
    await send_message(
        ctx.bot_token,
        ctx.chat_id,
        f"🔗 <b>Клиентский портал</b>\n{url}",
    )
