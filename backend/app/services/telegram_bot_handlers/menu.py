"""Telegram bot main menu — Reply Keyboard, inline nav, and text/callback routing."""

from __future__ import annotations

from app.services.feature_guards import get_feature_service
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.base import (
    BotContext,
    inline_button,
    inline_keyboard,
    is_admin,
    reply_button,
    reply_keyboard,
)
from app.services import telegram_bot_i18n as i18n

_ADMIN_ACTIONS = frozenset({"settings", "nodes", "cidr", "warper"})


def _admin_menu_visible(ctx: BotContext) -> bool:
    return is_admin(ctx.user)


def _cidr_visible(ctx: BotContext) -> bool:
    return _admin_menu_visible(ctx) and get_feature_service().is_enabled("routing")


def _warper_visible(ctx: BotContext) -> bool:
    return _admin_menu_visible(ctx) and get_feature_service().is_enabled("warper")


def _linked_user_menu_visible(ctx: BotContext) -> bool:
    return ctx.user is not None


def build_reply_keyboard(ctx: BotContext) -> dict:
    if not _linked_user_menu_visible(ctx):
        return reply_keyboard([[reply_button(i18n.BTN_MENU_HELP)]])

    row1 = [reply_button(i18n.BTN_MENU_STATUS), reply_button(i18n.BTN_MENU_CONFIGS)]
    row2: list[dict] = []
    if ctx.mini_app_url:
        row2.append(reply_button(i18n.BTN_OPEN_MINI_APP, web_app_url=ctx.mini_app_url))
    row2.append(reply_button(i18n.BTN_MENU_HELP))

    rows = [row1, row2]
    if _admin_menu_visible(ctx):
        admin_row = [reply_button(i18n.BTN_MENU_SETTINGS), reply_button(i18n.BTN_MENU_NODES)]
        rows.append(admin_row)
        module_row: list[dict] = []
        if _cidr_visible(ctx):
            module_row.append(reply_button(i18n.BTN_MENU_CIDR))
        if _warper_visible(ctx):
            module_row.append(reply_button(i18n.BTN_MENU_WARPER))
        if module_row:
            rows.append(module_row)
    return reply_keyboard(rows)


def build_main_inline_menu(ctx: BotContext) -> dict:
    if not _linked_user_menu_visible(ctx):
        return inline_keyboard([[inline_button(i18n.BTN_MENU_HELP, callback_data="nav:help")]])

    rows: list[list[dict]] = []
    if ctx.mini_app_url:
        rows.append([inline_button(i18n.BTN_OPEN_MINI_APP, url=ctx.mini_app_url)])

    rows.append(
        [
            inline_button(i18n.BTN_MENU_STATUS, callback_data="nav:status"),
            inline_button(i18n.BTN_MENU_CONFIGS, callback_data="nav:configs"),
        ]
    )
    rows.append([inline_button(i18n.BTN_MENU_HELP, callback_data="nav:help")])

    if _admin_menu_visible(ctx):
        admin_row = [
            inline_button(i18n.BTN_MENU_SETTINGS, callback_data="nav:settings"),
            inline_button(i18n.BTN_MENU_NODES, callback_data="nav:nodes"),
        ]
        rows.append(admin_row)
        module_row: list[dict] = []
        if _cidr_visible(ctx):
            module_row.append(inline_button(i18n.BTN_MENU_CIDR, callback_data="nav:cidr"))
        if _warper_visible(ctx):
            module_row.append(inline_button(i18n.BTN_MENU_WARPER, callback_data="nav:warper"))
        if module_row:
            rows.append(module_row)

    rows.append([inline_button(i18n.BTN_MENU_HOME, callback_data="nav:home")])
    return inline_keyboard(rows)


def build_bot_commands() -> list[dict[str, str]]:
    return [{"command": cmd, "description": desc} for cmd, desc in i18n.BOT_COMMANDS]


async def _dispatch_action(ctx: BotContext, action: str, *, message_id: int | None = None) -> None:
    if action in _ADMIN_ACTIONS and not is_admin(ctx.user):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return

    if action == "status":
        from app.services.telegram_bot_handlers.status import handle_status

        await handle_status(ctx, message_id=message_id)
    elif action == "configs":
        from app.services.telegram_bot_handlers.configs import handle_configs

        await handle_configs(ctx, message_id=message_id)
    elif action == "traffic":
        from app.services.telegram_bot_handlers.traffic import handle_traffic

        await handle_traffic(ctx, message_id=message_id)
    elif action == "help":
        from app.services.telegram_bot_handlers.help import handle_help

        await handle_help(ctx, message_id=message_id)
    elif action == "home":
        from app.services.telegram_bot_handlers.start import handle_start

        await handle_start(ctx)
    elif action == "settings":
        from app.services.telegram_bot_handlers.settings import handle_settings_root

        await handle_settings_root(ctx, message_id=message_id)
    elif action == "nodes":
        from app.services.telegram_bot_handlers.nodes import handle_nodes_root

        await handle_nodes_root(ctx, message_id=message_id)
    elif action == "cidr":
        from app.services.telegram_bot_handlers.cidr_status import handle_cidr_status

        await handle_cidr_status(ctx, message_id=message_id)
    elif action == "warper":
        from app.services.telegram_bot_handlers.warper_status import handle_warper_status

        await handle_warper_status(ctx, message_id=message_id)


async def handle_menu_text(ctx: BotContext, text: str) -> bool:
    action = i18n.MENU_ACTIONS.get((text or "").strip())
    if not action:
        return False
    await _dispatch_action(ctx, action)
    return True


async def handle_menu_callback(ctx: BotContext, data: str, *, message_id: int | None) -> bool:
    if not data.startswith("nav:"):
        return False
    action = data[len("nav:") :]
    if not action:
        return True
    await _dispatch_action(ctx, action, message_id=message_id)
    return True
