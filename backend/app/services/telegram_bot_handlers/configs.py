from __future__ import annotations

from app.services.telegram_api import edit_message_text, send_message
from app.services.telegram_bot_data import find_config_by_name, list_user_configs
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard, unlinked_message
from app.services import telegram_bot_i18n as i18n

_PAGE_SIZE = 8


def _configs_keyboard(configs: list, page: int) -> dict:
    start = page * _PAGE_SIZE
    chunk = configs[start : start + _PAGE_SIZE]
    rows = [
        [inline_button(f"{c.client_name} ({c.vpn_type.value})", callback_data=f"cfg:{c.id}")]
        for c in chunk
    ]
    nav: list = []
    if page > 0:
        nav.append(inline_button("◀️", callback_data=f"configs:{page - 1}"))
    if start + _PAGE_SIZE < len(configs):
        nav.append(inline_button("▶️", callback_data=f"configs:{page + 1}"))
    if nav:
        rows.append(nav)
    return inline_keyboard(rows)


async def handle_configs(ctx: BotContext, *, page: int = 0, message_id: int | None = None) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    configs = list_user_configs(ctx.db, ctx.user)
    if not configs:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIGS_NONE)
        return

    total_pages = max(1, (len(configs) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    text = i18n.CONFIGS_LIST.format(page=page + 1, total_pages=total_pages, count=len(configs))
    markup = _configs_keyboard(configs, page)
    if message_id is not None:
        await edit_message_text(ctx.bot_token, ctx.chat_id, message_id, text, reply_markup=markup)
    else:
        await send_message(ctx.bot_token, ctx.chat_id, text, reply_markup=markup)


async def handle_config(ctx: BotContext, name: str) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    config = find_config_by_name(ctx.db, ctx.user, name)
    if not config:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIG_NOT_FOUND.format(name=name))
        return

    rows = []
    if ctx.mini_app_url:
        rows.append([inline_button(i18n.BTN_OPEN_MINI_APP_CONFIG, url=ctx.mini_app_url)])
    rows.append([inline_button(i18n.BTN_ALL_CONFIGS, callback_data="configs:0")])
    text = i18n.CONFIG_CARD.format(
        name=config.client_name,
        vpn_type=config.vpn_type.value,
        config_id=config.id,
    )
    await send_message(ctx.bot_token, ctx.chat_id, text, reply_markup=inline_keyboard(rows))


async def handle_config_callback(ctx: BotContext, config_id: int) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    from app.models import VpnConfig
    from app.services.node_manager import get_active_node

    node = get_active_node(ctx.db)
    config = (
        ctx.db.query(VpnConfig)
        .filter(VpnConfig.id == config_id, VpnConfig.node_id == node.id)
        .first()
    )
    if not config:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIG_NOT_FOUND_ID)
        return
    if config.owner_id != ctx.user.id and ctx.user.role.value != "admin":
        await send_message(ctx.bot_token, ctx.chat_id, i18n.INSUFFICIENT_PERMISSIONS)
        return
    await handle_config(ctx, config.client_name)
