from __future__ import annotations

from app.services.feature_guards import get_feature_service
from app.services.telegram_bot_handlers.base import BotContext, is_admin
from app.services.telegram_bot_handlers.ui import nav_footer_keyboard, send_or_edit
from app.services import telegram_bot_i18n as i18n


def _help_text(ctx: BotContext) -> str:
    lines = [
        i18n.HELP_TITLE,
        "",
        i18n.HELP_SECTION_MAIN,
        *i18n.HELP_LINES_MAIN,
        "",
        i18n.HELP_SECTION_CONFIGS,
        *i18n.HELP_LINES_CONFIGS,
    ]
    if is_admin(ctx.user):
        lines.extend(["", i18n.HELP_SECTION_ADMIN, *i18n.HELP_LINES_ADMIN])
        if get_feature_service().is_enabled("routing"):
            lines.append(i18n.HELP_ADMIN_CIDR)
        if get_feature_service().is_enabled("warper"):
            lines.append(i18n.HELP_ADMIN_WARPER)
    lines.extend(["", i18n.HELP_FOOTER])
    return "\n".join(lines)


async def handle_help(ctx: BotContext, *, message_id: int | None = None) -> None:
    text = _help_text(ctx)
    markup = nav_footer_keyboard(refresh=None, include_help=False, include_home=True)
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)
