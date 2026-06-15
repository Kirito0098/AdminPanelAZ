from __future__ import annotations

from app.models import VpnConfig, VpnType
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.profile_download_name import enrich_profile_files
from app.services.telegram_api import send_message
from app.services.telegram_bot_handlers.ui import nav_footer_keyboard, send_or_edit
from app.services.telegram_bot_data import find_config_by_name, list_user_configs
from app.services.telegram_bot_handlers.base import BotContext, inline_button, inline_keyboard, unlinked_message
from app.services.telegram_config_send import send_config_for_user
from app.services.telegram_profile_ui import (
    ProfileFileGroup,
    build_profile_file_groups,
    file_button_label,
    find_group,
)
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
    extra_rows = list(rows)
    if nav:
        extra_rows.append(nav)
    return nav_footer_keyboard(refresh="nav:configs", extra_rows=extra_rows)


def _back_to_configs_row() -> list:
    return [inline_button(i18n.BTN_ALL_CONFIGS, callback_data="configs:0")]


def _config_root_keyboard(ctx: BotContext, config_id: int, groups: list[ProfileFileGroup]) -> dict:
    rows: list[list] = []
    for group in groups:
        count = len(group.files)
        label = f"{group.emoji} {group.title} ({count})"
        rows.append([inline_button(label, callback_data=f"cfgg:{config_id}:{group.key}")])
    rows.append(_back_to_configs_row())
    rows.append([inline_button(i18n.BTN_MENU_HOME, callback_data="nav:home")])
    if ctx.mini_app_url:
        rows.insert(0, [inline_button(i18n.BTN_OPEN_MINI_APP_CONFIG, url=ctx.mini_app_url)])
    return inline_keyboard(rows)


def _config_group_keyboard(ctx: BotContext, config_id: int, group: ProfileFileGroup) -> dict:
    rows: list[list] = []
    line: list = []
    for entry in group.files:
        line.append(inline_button(file_button_label(entry.file), callback_data=f"cfgf:{config_id}:{entry.index}"))
        if len(line) == 2:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    rows.append([inline_button(i18n.BTN_CONFIG_BACK, callback_data=f"cfg:{config_id}")])
    rows.append(_back_to_configs_row())
    rows.append([inline_button(i18n.BTN_MENU_HOME, callback_data="nav:home")])
    return inline_keyboard(rows)


def _after_send_keyboard(ctx: BotContext, config_id: int) -> dict:
    rows = [
        [inline_button(i18n.BTN_CONFIG_PICK_ANOTHER, callback_data=f"cfg:{config_id}")],
        _back_to_configs_row(),
        [inline_button(i18n.BTN_MENU_HOME, callback_data="nav:home")],
    ]
    if ctx.mini_app_url:
        rows.insert(0, [inline_button(i18n.BTN_OPEN_MINI_APP_CONFIG, url=ctx.mini_app_url)])
    return inline_keyboard(rows)


async def _get_accessible_config(ctx: BotContext, config_id: int) -> VpnConfig | None:
    node = get_active_node(ctx.db)
    config = (
        ctx.db.query(VpnConfig)
        .filter(VpnConfig.id == config_id, VpnConfig.node_id == node.id)
        .first()
    )
    if not config:
        return None
    if config.owner_id != ctx.user.id and ctx.user.role.value != "admin":
        return None
    return config


def _load_profile_groups(ctx: BotContext, config: VpnConfig) -> list[ProfileFileGroup]:
    adapter = get_active_adapter(ctx.db)
    raw_files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    return build_profile_file_groups(config.client_name, raw_files)


async def _show_config_picker(
    ctx: BotContext,
    config: VpnConfig,
    *,
    message_id: int | None = None,
) -> None:
    groups = _load_profile_groups(ctx, config)
    if not groups:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIG_FILES_NONE)
        return

    if len(groups) == 1 and len(groups[0].files) == 1:
        await handle_config_file_send(ctx, config.id, groups[0].files[0].index)
        return

    text = i18n.CONFIG_PICK_PROTOCOL.format(
        name=config.client_name,
        vpn_type=config.vpn_type.value,
    )
    await send_or_edit(
        ctx,
        text,
        markup=_config_root_keyboard(ctx, config.id, groups),
        message_id=message_id,
    )


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
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)


async def handle_config(ctx: BotContext, name: str) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    config = find_config_by_name(ctx.db, ctx.user, name)
    if not config:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIG_NOT_FOUND.format(name=name))
        return

    await _show_config_picker(ctx, config)


async def handle_config_callback(ctx: BotContext, config_id: int, *, message_id: int | None = None) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    config = await _get_accessible_config(ctx, config_id)
    if not config:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIG_NOT_FOUND_ID)
        return

    await _show_config_picker(ctx, config, message_id=message_id)


async def handle_config_group_callback(
    ctx: BotContext,
    config_id: int,
    group_key: str,
    *,
    message_id: int | None = None,
) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    config = await _get_accessible_config(ctx, config_id)
    if not config:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIG_NOT_FOUND_ID)
        return

    groups = _load_profile_groups(ctx, config)
    group = find_group(groups, group_key)
    if group is None:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIG_GROUP_NOT_FOUND)
        return

    if len(group.files) == 1:
        await handle_config_file_send(ctx, config_id, group.files[0].index, message_id=message_id)
        return

    text = i18n.CONFIG_PICK_FILE.format(
        name=config.client_name,
        protocol=f"{group.emoji} {group.title}",
    )
    await send_or_edit(
        ctx,
        text,
        markup=_config_group_keyboard(ctx, config_id, group),
        message_id=message_id,
    )


async def handle_config_file_send(
    ctx: BotContext,
    config_id: int,
    file_index: int,
    *,
    message_id: int | None = None,
) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    config = await _get_accessible_config(ctx, config_id)
    if not config:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIG_NOT_FOUND_ID)
        return

    adapter = get_active_adapter(ctx.db)
    raw_files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    enriched = enrich_profile_files(config.client_name, raw_files)
    if file_index < 0 or file_index >= len(enriched):
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIG_FILE_NOT_FOUND)
        return

    selected = enriched[file_index]
    path = selected.get("path")
    sent, error = send_config_for_user(
        ctx.db,
        config,
        ctx.user,
        bot_token=ctx.bot_token,
        path=path,
        chat_id_override=ctx.chat_id,
        run_async=False,
    )
    if sent == 0:
        await send_message(
            ctx.bot_token,
            ctx.chat_id,
            i18n.CONFIG_SEND_FAILED.format(detail=error or i18n.CONFIG_SEND_UNKNOWN),
        )
        return

    await send_or_edit(
        ctx,
        i18n.CONFIG_SEND_OK_ONE.format(name=config.client_name),
        markup=_after_send_keyboard(ctx, config_id),
        message_id=message_id,
    )
