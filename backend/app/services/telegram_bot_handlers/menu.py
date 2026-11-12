"""Telegram bot main menu — Reply Keyboard, inline nav, and text/callback routing."""

from __future__ import annotations

import logging

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
from app.services.telegram_bot_handlers.ui import send_or_edit
from app.services import telegram_bot_i18n as i18n
from app.services.telegram_bot_handlers import settings_fsm
from app.services.user_access_requests import _accept_requests

_ADMIN_ACTIONS = frozenset({"status", "settings", "nodes", "cidr", "warper", "awg2", "unlock"})

logger = logging.getLogger(__name__)


def _unlock_codes_enabled() -> bool:
    try:
        return get_feature_service().is_enabled("unlock_codes")
    except Exception:  # noqa: BLE001 — раскладка меню не должна падать из-за чтения тоглов
        logger.warning("menu: unlock_codes feature check failed", exc_info=True)
        return False


def _linked_user_menu_visible(ctx: BotContext) -> bool:
    return ctx.user is not None


def _menu_button_label(action: str) -> str:
    return {
        "status": i18n.BTN_MENU_STATUS,
        "overview": i18n.BTN_MENU_OVERVIEW,
        "configs": i18n.BTN_MENU_CONFIGS,
        "more": i18n.BTN_MENU_MORE,
        "traffic": i18n.BTN_MENU_TRAFFIC,
        "help": i18n.BTN_MENU_HELP,
        "settings": i18n.BTN_MENU_SETTINGS,
        "nodes": i18n.BTN_MENU_NODES,
        "cidr": i18n.BTN_MENU_CIDR,
        "warper": i18n.BTN_MENU_WARPER,
        "awg2": i18n.BTN_MENU_AWG2,
        "unlock": i18n.BTN_MENU_UNLOCK_CODES,
        "redeem_unlock": i18n.BTN_REDEEM_UNLOCK,
        "request_more_config": i18n.BTN_REQUEST_MORE_CONFIG,
    }[action]


def _action_visible(ctx: BotContext, action: str) -> bool:
    """Модульные действия скрыты, если их фича выключена (как и раньше в меню)."""
    if action in _ADMIN_ACTIONS and not is_admin(ctx.user):
        return False
    if action == "cidr":
        return get_feature_service().is_enabled("routing")
    if action == "warper":
        return get_feature_service().is_enabled("warper")
    if action == "awg2":
        return get_feature_service().is_enabled("awg2")
    if action in {"unlock", "redeem_unlock"}:
        return get_feature_service().is_enabled("unlock_codes")
    return True


def _more_menu_row_actions(ctx: BotContext) -> list[list[str]]:
    """Второстепенные разделы: у админа — модули, у абонента — свои действия."""
    rows: list[list[str]] = []
    if is_admin(ctx.user):
        modules = [action for action in ("cidr", "warper", "awg2") if _action_visible(ctx, action)]
        if modules:
            rows.append(modules)
        if _action_visible(ctx, "unlock"):
            rows.append(["unlock"])
        rows.append(["help"])
        return rows
    if _action_visible(ctx, "redeem_unlock"):
        rows.append(["redeem_unlock"])
    rows.append(["request_more_config"])
    rows.append(["help"])
    return rows


def _user_messaging_enabled() -> bool:
    try:
        return get_feature_service().is_enabled("user_messaging")
    except Exception:  # noqa: BLE001 — раскладка меню не должна падать из-за тоглов
        logger.warning("menu: user_messaging feature check failed", exc_info=True)
        return False


def build_linked_reply_keyboard(
    *, is_admin: bool = False, in_chat: bool = False, show_pay: bool = False
) -> dict:
    """Компактная reply-клавиатура: частые действия внизу, остальное — в hub-виджете.

    Убранные кнопки (оплата, чат, коды, «Ещё») живут в меню-виджете, поэтому
    нижняя панель занимает две строки вместо четырёх. Используется и после
    одобрения заявки, чтобы устаревшая кнопка «Запросить доступ» пропала.
    """
    del show_pay  # оплата теперь в hub-виджете
    if is_admin:
        rows = [
            [reply_button(i18n.BTN_MENU_HUB), reply_button(i18n.BTN_MENU_CONFIGS)],
            [reply_button(i18n.BTN_MENU_TRAFFIC), reply_button(i18n.BTN_MENU_SETTINGS)],
        ]
    else:
        rows = [
            [reply_button(i18n.BTN_MENU_HUB), reply_button(i18n.BTN_MENU_CONFIGS)],
            [reply_button(i18n.BTN_MENU_TRAFFIC), reply_button(i18n.BTN_MENU_HELP)],
        ]
        if in_chat:
            rows.append([reply_button(i18n.BTN_CHAT_STOP)])
    return reply_keyboard(rows, placeholder=i18n.MENU_KEYBOARD_PLACEHOLDER)


def build_reply_keyboard(ctx: BotContext) -> dict:
    if not _linked_user_menu_visible(ctx):
        rows = [[reply_button(i18n.BTN_MENU_HUB), reply_button(i18n.BTN_LINK_CODE)]]
        if _accept_requests(ctx.db):
            rows.append([reply_button(i18n.BTN_REQUEST_ACCESS)])
        return reply_keyboard(rows, placeholder=i18n.MENU_KEYBOARD_PLACEHOLDER)

    return build_linked_reply_keyboard(
        is_admin=is_admin(ctx.user),
        in_chat=ctx.user.chat_mode_since is not None,
        show_pay=_accept_requests(ctx.db),
    )


def build_more_inline_menu(ctx: BotContext) -> dict:
    rows = [
        [inline_button(_menu_button_label(action), callback_data=f"nav:{action}") for action in spec_row]
        for spec_row in _more_menu_row_actions(ctx)
    ]
    return inline_keyboard(rows)


async def handle_more_menu(ctx: BotContext, *, message_id: int | None = None) -> None:
    await send_or_edit(
        ctx,
        i18n.MENU_MORE_TITLE,
        markup=build_more_inline_menu(ctx),
        message_id=message_id,
    )


async def _dispatch_action(ctx: BotContext, action: str, *, message_id: int | None = None) -> None:
    if action in _ADMIN_ACTIONS and not is_admin(ctx.user):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return

    # Любая кнопка/навигация выводит из режима переписки (кроме входа в него).
    if action != "admin_chat" and ctx.user is not None:
        from app.services.user_messages import leave_chat_mode

        leave_chat_mode(ctx.db, ctx.user)

    if action == "more":
        await handle_more_menu(ctx, message_id=message_id)
    elif action == "admin_chat":
        from app.services.telegram_bot_handlers.chat import handle_admin_chat

        await handle_admin_chat(ctx)
    elif action == "chat_stop":
        from app.services.telegram_bot_handlers.chat import handle_chat_stop

        await handle_chat_stop(ctx)
    elif action == "pay_request":
        from app.services.telegram_bot_handlers.access_requests import handle_pay_request

        await handle_pay_request(ctx)
    elif action == "status":
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
    elif action == "awg2":
        from app.services.telegram_bot_handlers.awg2_status import handle_awg2_status

        await handle_awg2_status(ctx, message_id=message_id)
    elif action == "unlock":
        from app.services.telegram_bot_handlers.unlock_codes import handle_unlock_codes_root

        await handle_unlock_codes_root(ctx, message_id=message_id)
    elif action == "request_access":
        from app.services.telegram_bot_handlers.access_requests import (
            handle_request_access,
        )

        await handle_request_access(ctx)
    elif action == "request_more_config":
        from app.services.telegram_bot_handlers.access_requests import (
            handle_request_more_config,
        )

        await handle_request_more_config(ctx)
    elif action == "redeem_unlock":
        if not get_feature_service().is_enabled("unlock_codes"):
            await send_message(ctx.bot_token, ctx.chat_id, "Раздел кодов доступа отключён.")
            return
        from app.services.telegram_bot_handlers.user_renew import start_redeem_prompt

        await start_redeem_prompt(ctx.bot_token, str(ctx.chat_id))
    elif action == "link_code":
        await send_message(ctx.bot_token, ctx.chat_id, i18n.REQUEST_LINK_HINT)


async def handle_menu_text(ctx: BotContext, text: str) -> bool:
    action = i18n.MENU_ACTIONS.get((text or "").strip())
    if not action:
        return False
    settings_fsm.clear_pending(ctx.telegram_user_id)
    await _dispatch_action(ctx, action)
    return True


async def handle_menu_callback(ctx: BotContext, data: str, *, message_id: int | None) -> bool:
    if not data.startswith("nav:"):
        return False
    action = data[len("nav:") :]
    if not action:
        return True
    settings_fsm.clear_pending(ctx.telegram_user_id)
    await _dispatch_action(ctx, action, message_id=message_id)
    return True
