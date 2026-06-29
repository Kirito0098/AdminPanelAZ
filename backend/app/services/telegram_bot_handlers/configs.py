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
    GROUP_META,
    ProfileFileGroup,
    build_profile_file_groups,
    file_button_label,
    find_group,
    file_preview_line,
    protocol_group_key,
)
from app.services import telegram_bot_i18n as i18n

_PAGE_SIZE = 12
_COLUMNS = 2
_NAME_MAX_LEN = 24
_VALID_FILTERS = frozenset({"all", "ovpn", "wg", "awg"})
_FILTER_VPN_TYPE = {
    "ovpn": VpnType.openvpn,
    "wg": VpnType.wireguard,
}
_FILTER_LABELS = {
    "all": i18n.CONFIGS_FILTER_ALL,
    "ovpn": i18n.CONFIGS_FILTER_OVPN,
    "wg": i18n.CONFIGS_FILTER_WG,
    "awg": i18n.CONFIGS_FILTER_AWG,
}


def parse_configs_callback(data: str) -> tuple[int, str]:
    parts = data.split(":")
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    filter_key = parts[2] if len(parts) > 2 and parts[2] in _VALID_FILTERS else "all"
    return page, filter_key


def _vpn_emoji(vpn_type: VpnType) -> str:
    key = protocol_group_key(vpn_type.value)
    return GROUP_META.get(key, ("📄", ""))[0]


def _short_name(name: str, *, max_len: int = _NAME_MAX_LEN) -> str:
    if len(name) <= max_len:
        return name
    return name[: max_len - 1] + "…"


def _config_button_label(config: VpnConfig) -> str:
    return f"{_vpn_emoji(config.vpn_type)} {_short_name(config.client_name)}"


def _count_by_protocol(configs: list[VpnConfig]) -> dict[str, int]:
    counts = {"ovpn": 0, "wg": 0, "awg": 0}
    for config in configs:
        key = protocol_group_key(config.vpn_type.value)
        if key in counts:
            counts[key] += 1
    return counts


def _filter_configs(configs: list[VpnConfig], filter_key: str) -> list[VpnConfig]:
    if filter_key == "all":
        return configs
    if filter_key == "awg":
        return [c for c in configs if protocol_group_key(c.vpn_type.value) == "awg"]
    vpn_type = _FILTER_VPN_TYPE.get(filter_key)
    if vpn_type is None:
        return configs
    return [c for c in configs if c.vpn_type == vpn_type]


def _chunk_buttons(buttons: list[dict], columns: int = _COLUMNS) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for index in range(0, len(buttons), columns):
        rows.append(buttons[index : index + columns])
    return rows


def _build_filter_rows(counts: dict[str, int], current: str) -> list[list[dict]]:
    active_types = [key for key in ("ovpn", "wg", "awg") if counts.get(key, 0) > 0]
    if len(active_types) < 2:
        return []

    buttons: list[dict] = []
    if current == "all":
        buttons.append(inline_button("✓ 📁 Все", callback_data="configs:0:all"))
    else:
        buttons.append(inline_button("📁 Все", callback_data="configs:0:all"))

    for key in active_types:
        emoji, _title = GROUP_META[key]
        count = counts[key]
        label = f"✓ {emoji} {count}" if current == key else f"{emoji} {count}"
        buttons.append(inline_button(label, callback_data=f"configs:0:{key}"))
    return _chunk_buttons(buttons, columns=3)


def _configs_preview(chunk: list[VpnConfig], start_index: int) -> str:
    lines = [
        f"{start_index + offset}. {_vpn_emoji(config.vpn_type)} <code>{config.client_name}</code>"
        for offset, config in enumerate(chunk)
    ]
    return "\n".join(lines)


def _configs_keyboard(
    configs: list[VpnConfig],
    *,
    page: int,
    filter_key: str,
) -> dict:
    filtered = _filter_configs(configs, filter_key)
    counts = _count_by_protocol(configs)
    total_pages = max(1, (len(filtered) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _PAGE_SIZE
    chunk = filtered[start : start + _PAGE_SIZE]

    rows: list[list[dict]] = []
    rows.extend(_build_filter_rows(counts, filter_key))

    config_buttons = [
        inline_button(_config_button_label(config), callback_data=f"cfg:{config.id}") for config in chunk
    ]
    rows.extend(_chunk_buttons(config_buttons))

    if total_pages > 1:
        nav: list[dict] = []
        if page > 0:
            nav.append(inline_button("◀️", callback_data=f"configs:{page - 1}:{filter_key}"))
        nav.append(inline_button(f"· {page + 1}/{total_pages} ·", callback_data=f"configs:{page}:{filter_key}"))
        if start + _PAGE_SIZE < len(filtered):
            nav.append(inline_button("▶️", callback_data=f"configs:{page + 1}:{filter_key}"))
        rows.append(nav)

    return nav_footer_keyboard(refresh=f"configs:{page}:{filter_key}", extra_rows=rows)


def _back_to_configs_row() -> list:
    return [inline_button(i18n.BTN_ALL_CONFIGS, callback_data="configs:0:all")]


def _config_root_keyboard(ctx: BotContext, config_id: int, groups: list[ProfileFileGroup]) -> dict:
    rows: list[list] = []
    for group in groups:
        count = len(group.files)
        label = f"{group.emoji} {group.title} ({count})"
        rows.append([inline_button(label, callback_data=f"cfgg:{config_id}:{group.key}")])
    rows.append(_back_to_configs_row())
    rows.append([inline_button(i18n.BTN_MENU_HOME, callback_data="nav:home")])
    return inline_keyboard(rows)


def _config_group_keyboard(config_id: int, group: ProfileFileGroup) -> dict:
    rows: list[list] = [
        [inline_button(file_button_label(entry.file, index=offset), callback_data=f"cfgf:{config_id}:{entry.index}")]
        for offset, entry in enumerate(group.files, start=1)
    ]
    rows.append(
        [
            inline_button(i18n.BTN_CONFIG_BACK, callback_data=f"cfg:{config_id}"),
            inline_button(i18n.BTN_ALL_CONFIGS, callback_data="configs:0:all"),
        ]
    )
    rows.append([inline_button(i18n.BTN_MENU_HOME, callback_data="nav:home")])
    return inline_keyboard(rows)


def _after_send_keyboard(ctx: BotContext, config_id: int) -> dict:
    rows = [
        [inline_button(i18n.BTN_CONFIG_PICK_ANOTHER, callback_data=f"cfg:{config_id}")],
        _back_to_configs_row(),
        [inline_button(i18n.BTN_MENU_HOME, callback_data="nav:home")],
    ]
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


async def handle_configs(
    ctx: BotContext,
    *,
    page: int = 0,
    filter_key: str = "all",
    message_id: int | None = None,
) -> None:
    if ctx.user is None:
        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return

    configs = list_user_configs(ctx.db, ctx.user)
    if not configs:
        await send_message(ctx.bot_token, ctx.chat_id, i18n.CONFIGS_NONE)
        return

    if filter_key not in _VALID_FILTERS:
        filter_key = "all"

    filtered = _filter_configs(configs, filter_key)
    if not filtered:
        filter_key = "all"
        filtered = configs

    total_pages = max(1, (len(filtered) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _PAGE_SIZE
    chunk = filtered[start : start + _PAGE_SIZE]

    counts = _count_by_protocol(configs)
    active_types = sum(1 for key in ("ovpn", "wg", "awg") if counts.get(key, 0) > 0)
    hint = i18n.CONFIGS_FILTER_HINT if active_types > 1 and filter_key == "all" and len(configs) > _PAGE_SIZE else ""

    text = i18n.CONFIGS_LIST.format(
        filter_label=_FILTER_LABELS.get(filter_key, i18n.CONFIGS_FILTER_ALL),
        page=page + 1,
        total_pages=total_pages,
        count=len(filtered),
        hint=hint,
        preview=_configs_preview(chunk, start),
    )
    markup = _configs_keyboard(configs, page=page, filter_key=filter_key)
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

    preview = "\n".join(file_preview_line(offset, entry.file) for offset, entry in enumerate(group.files, start=1))
    text = i18n.CONFIG_PICK_FILE.format(
        name=config.client_name,
        protocol=f"{group.emoji} <b>{group.title}</b>",
        preview=preview,
    )
    await send_or_edit(
        ctx,
        text,
        markup=_config_group_keyboard(config_id, group),
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
