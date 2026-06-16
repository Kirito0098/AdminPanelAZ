"""Telegram bot update dispatcher."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.routers.maintenance import _get_setting
from app.services.telegram_api import answer_callback_query
from app.services.telegram_bot_handlers.base import BotContext, resolve_user
from app.services.telegram_bot_handlers.configs import (
    handle_config,
    handle_config_callback,
    handle_configs,
)
from app.services.telegram_bot_handlers.cidr_status import handle_cidr_status
from app.services.telegram_bot_handlers.help import handle_help
from app.services.telegram_bot_handlers.link import handle_link
from app.services.telegram_bot_handlers.nodes import (
    handle_node_activate,
    handle_node_detail,
    handle_node_health,
    handle_nodes_root,
)
from app.services.telegram_bot_handlers.settings import (
    handle_settings_callback,
    handle_settings_root,
    handle_settings_text,
)
from app.services.telegram_bot_handlers.start import handle_start
from app.services.telegram_bot_handlers.menu import handle_menu_callback, handle_menu_text
from app.services.telegram_bot_handlers.ui import handle_unknown_text, nav_footer_keyboard
from app.services.telegram_bot_handlers.status import handle_status
from app.services.telegram_bot_handlers.warper_status import handle_warper_status
from app.services.telegram_bot_handlers.traffic import handle_traffic
from app.services.telegram_bot_handlers.inline import handle_chosen_inline_result, handle_inline_query
from app.services.telegram_bot_command_rate_limit import telegram_bot_command_rate_limit_service
from app.services import telegram_bot_i18n as i18n

logger = logging.getLogger(__name__)

_PUBLIC_COMMANDS = frozenset({"/start", "/help", "/link"})


def _is_interactive_enabled(db: Session) -> bool:
    return _get_setting(db, "telegram_bot_interactive_enabled", "false") == "true"


def _parse_command(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return "", ""
    parts = raw.split(maxsplit=1)
    command = parts[0].split("@")[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return command, args


def _build_context(db: Session, *, chat_id: int | str, telegram_user_id: str, mini_app_url: str) -> BotContext:
    bot_token = _get_setting(db, "telegram_bot_token")
    user = resolve_user(db, telegram_user_id)
    return BotContext(
        db=db,
        bot_token=bot_token,
        chat_id=chat_id,
        telegram_user_id=telegram_user_id,
        user=user,
        mini_app_url=mini_app_url,
    )


async def _dispatch_command(ctx: BotContext, command: str, args: str) -> None:
    if command == "/start":
        await handle_start(ctx)
        return
    if command == "/help":
        await handle_help(ctx)
        return
    if command == "/link":
        await handle_link(ctx, args)
        return

    if ctx.user is None and command not in _PUBLIC_COMMANDS:
        from app.services.telegram_api import send_message
        from app.services.telegram_bot_handlers.base import unlinked_message

        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    rate_error = telegram_bot_command_rate_limit_service.consume(ctx.db, ctx.telegram_user_id)
    if rate_error:
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, rate_error)
        return

    if command == "/status":
        await handle_status(ctx)
    elif command == "/configs" or command == "/myconfigs":
        await handle_configs(ctx)
    elif command == "/traffic":
        await handle_traffic(ctx)
    elif command == "/config":
        await handle_config(ctx, args)
    elif command == "/settings":
        await handle_settings_root(ctx)
    elif command == "/cidr":
        await handle_cidr_status(ctx)
    elif command == "/nodes":
        await handle_nodes_root(ctx)
    elif command == "/warper":
        await handle_warper_status(ctx)
    else:
        from app.services.telegram_api import send_message

        await send_message(
            ctx.bot_token,
            ctx.chat_id,
            i18n.UNKNOWN_COMMAND,
            reply_markup=nav_footer_keyboard(refresh=None, include_help=True, include_home=True),
        )


async def _dispatch_callback(ctx: BotContext, data: str, *, message_id: int | None) -> None:
    if await handle_menu_callback(ctx, data, message_id=message_id):
        return
    if data == "help":
        await handle_help(ctx, message_id=message_id)
        return
    if data.startswith("configs:"):
        page = int(data.split(":", 1)[1]) if data.split(":", 1)[1].isdigit() else 0
        await handle_configs(ctx, page=page, message_id=message_id)
        return
    if data.startswith("traffic:"):
        page = int(data.split(":", 1)[1]) if data.split(":", 1)[1].isdigit() else 0
        await handle_traffic(ctx, page=page, message_id=message_id)
        return
    if data.startswith("cfgf:"):
        parts = data.split(":")
        config_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        file_index = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else -1
        from app.services.telegram_bot_handlers.configs import handle_config_file_send

        await handle_config_file_send(ctx, config_id, file_index, message_id=message_id)
        return
    if data.startswith("cfgg:"):
        parts = data.split(":")
        config_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        group_key = parts[2] if len(parts) > 2 else ""
        from app.services.telegram_bot_handlers.configs import handle_config_group_callback

        await handle_config_group_callback(ctx, config_id, group_key, message_id=message_id)
        return
    if data.startswith("cfg:"):
        config_id = int(data.split(":", 1)[1]) if data.split(":", 1)[1].isdigit() else 0
        await handle_config_callback(ctx, config_id, message_id=message_id)
        return
    if data.startswith("st:"):
        await handle_settings_callback(ctx, data, message_id=message_id)
        return
    if data.startswith("nodes:"):
        page = int(data.split(":", 1)[1]) if data.split(":", 1)[1].isdigit() else 0
        await handle_nodes_root(ctx, page=page, message_id=message_id)
        return
    if data.startswith("ndh:"):
        node_id = int(data.split(":", 1)[1]) if data.split(":", 1)[1].isdigit() else 0
        await handle_node_health(ctx, node_id, message_id=message_id)
        return
    if data.startswith("nda:"):
        node_id = int(data.split(":", 1)[1]) if data.split(":", 1)[1].isdigit() else 0
        await handle_node_activate(ctx, node_id, message_id=message_id)
        return
    if data.startswith("nd:"):
        node_id = int(data.split(":", 1)[1]) if data.split(":", 1)[1].isdigit() else 0
        await handle_node_detail(ctx, node_id, message_id=message_id)
        return


class TelegramBotService:
    async def handle_update(self, db: Session, update: dict[str, Any], *, mini_app_url: str) -> None:
        if not _is_interactive_enabled(db):
            return

        bot_token = _get_setting(db, "telegram_bot_token")
        if not bot_token:
            return

        callback = update.get("callback_query")
        if callback:
            await self._handle_callback(db, callback, mini_app_url=mini_app_url)
            return

        inline_query = update.get("inline_query")
        if inline_query:
            await self._handle_inline_query(db, inline_query, mini_app_url=mini_app_url)
            return

        chosen = update.get("chosen_inline_result")
        if chosen:
            await self._handle_chosen_inline_result(db, chosen, mini_app_url=mini_app_url)
            return

        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        text = message.get("text") or ""
        command, args = _parse_command(text)

        from_user = message.get("from") or {}
        chat = message.get("chat") or {}
        telegram_user_id = str(from_user.get("id", ""))
        chat_id = chat.get("id", telegram_user_id)
        if not telegram_user_id:
            return

        ctx = _build_context(
            db,
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            mini_app_url=mini_app_url,
        )

        if not command:
            if text.strip() and await handle_settings_text(ctx, text):
                return
            if text.strip() and await handle_menu_text(ctx, text):
                return
            if text.strip():
                await handle_unknown_text(ctx)
            return

        await _dispatch_command(ctx, command, args)

    async def _handle_callback(self, db: Session, callback: dict[str, Any], *, mini_app_url: str) -> None:
        bot_token = _get_setting(db, "telegram_bot_token")
        callback_id = str(callback.get("id", ""))
        data = str(callback.get("data") or "")
        from_user = callback.get("from") or {}
        message = callback.get("message") or {}
        telegram_user_id = str(from_user.get("id", ""))
        chat = message.get("chat") or {}
        chat_id = chat.get("id", telegram_user_id)
        message_id = message.get("message_id")

        if callback_id:
            await answer_callback_query(bot_token, callback_id)

        if not data or not telegram_user_id:
            return

        ctx = _build_context(
            db,
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            mini_app_url=mini_app_url,
        )
        if ctx.user is None and not (data == "help" or data.startswith("nav:help")):
            from app.services.telegram_api import send_message
            from app.services.telegram_bot_handlers.base import unlinked_message

            await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
            return

        await _dispatch_callback(ctx, data, message_id=message_id)

    async def _handle_inline_query(
        self,
        db: Session,
        inline_query: dict[str, Any],
        *,
        mini_app_url: str,
    ) -> None:
        from_user = inline_query.get("from") or {}
        telegram_user_id = str(from_user.get("id", ""))
        if not telegram_user_id:
            return

        ctx = _build_context(
            db,
            chat_id=telegram_user_id,
            telegram_user_id=telegram_user_id,
            mini_app_url=mini_app_url,
        )
        await handle_inline_query(ctx, inline_query)

    async def _handle_chosen_inline_result(
        self,
        db: Session,
        chosen: dict[str, Any],
        *,
        mini_app_url: str,
    ) -> None:
        from_user = chosen.get("from") or {}
        telegram_user_id = str(from_user.get("id", ""))
        if not telegram_user_id:
            return

        ctx = _build_context(
            db,
            chat_id=telegram_user_id,
            telegram_user_id=telegram_user_id,
            mini_app_url=mini_app_url,
        )
        if ctx.user is None:
            return

        await handle_chosen_inline_result(ctx, chosen)


telegram_bot_service = TelegramBotService()
