from __future__ import annotations

from app.services.telegram_api import edit_message_text, send_message
from app.services.feature_guards import get_feature_service
from app.services.telegram_bot_handlers.base import BotContext, is_admin
from app.services import telegram_bot_i18n as i18n


def _help_text(user: BotContext) -> str:
    lines = [i18n.HELP_TITLE, "", *i18n.HELP_LINES]
    if is_admin(user.user):
        lines.extend(
            [
                i18n.HELP_ADMIN_SETTINGS,
                i18n.HELP_ADMIN_CIDR,
            ]
        )
        if get_feature_service().is_enabled("warper"):
            lines.append(i18n.HELP_ADMIN_WARPER)
        lines.append(i18n.HELP_ADMIN_FOOTER)
    return "\n".join(lines)


async def handle_help(ctx: BotContext, *, message_id: int | None = None) -> None:
    text = _help_text(ctx)
    if message_id is not None:
        await edit_message_text(ctx.bot_token, ctx.chat_id, message_id, text)
    else:
        await send_message(ctx.bot_token, ctx.chat_id, text)
