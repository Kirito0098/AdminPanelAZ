"""Shared Telegram bot UI helpers — navigation, formatting, send/edit."""

from __future__ import annotations

from datetime import datetime

from app.services.telegram_api import edit_message_text, send_message
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard
from app.services import telegram_bot_i18n as i18n

# Telegram requires non-empty text; invisible separator for keyboard-only messages.
INVISIBLE_TEXT = "\u200b"

ROLE_LABELS: dict[str, str] = {
    "admin": "Администратор",
    "user": "Пользователь",
}


def role_label(role: str | None) -> str:
    value = (role or "").strip().lower()
    return ROLE_LABELS.get(value, value or "—")


def format_bot_timestamp(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return "—"
    try:
        normalized = text.replace("Z", "+00:00")
        if "T" not in normalized and " " in normalized:
            normalized = normalized.replace(" ", "T", 1)
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%d.%m.%Y %H:%M UTC")
    except ValueError:
        return text[:19]


async def send_or_edit(
    ctx: BotContext,
    text: str,
    *,
    markup: dict | None = None,
    message_id: int | None = None,
) -> None:
    if message_id is not None:
        await edit_message_text(ctx.bot_token, ctx.chat_id, message_id, text, reply_markup=markup)
    else:
        await send_message(ctx.bot_token, ctx.chat_id, text, reply_markup=markup)


def nav_footer_keyboard(
    *,
    refresh: str | None = None,
    include_help: bool = True,
    include_home: bool = True,
    extra_rows: list[list[dict]] | None = None,
) -> dict:
    """Standard inline footer: optional refresh + help + home."""
    footer: list[dict] = []
    if include_home:
        footer.append(inline_button(i18n.BTN_MENU_HOME, callback_data="nav:home"))
    if refresh:
        footer.append(inline_button(i18n.BTN_REFRESH, callback_data=refresh))
    if include_help:
        footer.append(inline_button(i18n.BTN_HELP, callback_data="nav:help"))

    rows = [list(row) for row in (extra_rows or [])]
    if footer:
        rows.append(footer)
    return inline_keyboard(rows)


async def send_hint(ctx: BotContext, text: str, *, markup: dict | None = None) -> None:
    await send_message(ctx.bot_token, ctx.chat_id, text, reply_markup=markup)


async def handle_unknown_text(ctx: BotContext) -> None:
    await send_hint(
        ctx,
        i18n.UNKNOWN_TEXT,
        markup=nav_footer_keyboard(refresh=None, include_help=True, include_home=True),
    )
