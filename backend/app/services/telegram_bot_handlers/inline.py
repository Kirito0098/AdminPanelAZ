"""Telegram bot inline query — search configs and share links/files."""

from __future__ import annotations

import logging
from typing import Any

from app.models import AppSetting, VpnConfig, VpnType
from app.services.node_manager import get_active_adapter
from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files
from app.services.qr_download import QrDownloadService
from app.services.security import SecurityService
from app.services.telegram_api import answer_inline_query
from app.services.telegram_bot_data import search_user_configs
from app.services.telegram_bot_handlers.base import BotContext, unlinked_message
from app.services.telegram_bot_inline_cache import (
    INLINE_RESULTS_TTL_SECONDS,
    get_cached_inline_results,
    inline_results_cache_key,
)
from app.services import telegram_bot_i18n as i18n

logger = logging.getLogger(__name__)

_MAX_INLINE_RESULTS = 20
_MINI_APP_QUERY_HINTS = frozenset({"app", "mini", "miniapp", "panel"})


def _panel_base_url(mini_app_url: str) -> str:
    return (mini_app_url or "").removesuffix("/api/tg-mini").rstrip("/")


def _mime_type_for_path(path: str) -> str:
    lowered = (path or "").lower()
    if lowered.endswith(".ovpn"):
        return "application/x-openvpn-profile"
    if lowered.endswith(".conf"):
        return "text/plain"
    return "application/octet-stream"


def _mini_app_article(ctx: BotContext) -> dict[str, Any] | None:
    if not ctx.mini_app_url:
        return None
    return {
        "type": "article",
        "id": "miniapp",
        "title": i18n.INLINE_MINI_APP_TITLE,
        "description": i18n.INLINE_MINI_APP_DESC,
        "input_message_content": {
            "message_text": i18n.INLINE_MINI_APP_MESSAGE.format(mini_app_url=ctx.mini_app_url),
            "parse_mode": "HTML",
        },
        "reply_markup": {
            "inline_keyboard": [[{"text": i18n.BTN_OPEN_MINI_APP, "url": ctx.mini_app_url}]],
        },
    }


def _unlinked_article() -> dict[str, Any]:
    return {
        "type": "article",
        "id": "unlinked",
        "title": i18n.INLINE_UNLINKED_TITLE,
        "description": i18n.INLINE_UNLINKED_DESC,
        "input_message_content": {
            "message_text": unlinked_message(),
            "parse_mode": "HTML",
        },
    }


def _create_download_url(ctx: BotContext, config: VpnConfig, path: str) -> str | None:
    base_url = _panel_base_url(ctx.mini_app_url)
    if not base_url or ctx.user is None:
        return None
    sec = SecurityService().get_settings(ctx.db)
    pin_row = ctx.db.query(AppSetting).filter(AppSetting.key == "qr_download_pin").first()
    service = QrDownloadService(
        ctx.db,
        base_url=base_url,
        ttl_seconds=sec["qr_download_ttl_seconds"],
        max_downloads=sec["qr_download_max_downloads"],
        pin=pin_row.value if pin_row else "",
    )
    payload = service.create_token(
        file_path=path,
        config_type=config.vpn_type.value,
        config_name=build_profile_download_filename(config.client_name, path=path),
        creator_id=ctx.user.id,
        creator_username=ctx.user.username,
    )
    return payload.get("url")


def _config_document_result(ctx: BotContext, config: VpnConfig, file_item: dict[str, str]) -> dict[str, Any] | None:
    path = file_item.get("path") or ""
    if not path:
        return None
    download_url = _create_download_url(ctx, config, path)
    if not download_url:
        return None
    filename = file_item.get("download_filename") or build_profile_download_filename(
        config.client_name,
        protocol=file_item.get("protocol", ""),
        variant=file_item.get("variant", ""),
        path=path,
    )
    return {
        "type": "document",
        "id": f"cfg:{config.id}:{path}",
        "title": config.client_name,
        "document_url": download_url,
        "mime_type": _mime_type_for_path(path),
        "description": i18n.INLINE_CONFIG_DESC.format(
            name=config.client_name,
            vpn_type=config.vpn_type.value,
            filename=filename,
        ),
    }


def _config_article_fallback(ctx: BotContext, config: VpnConfig) -> dict[str, Any]:
    message = i18n.INLINE_CONFIG_MESSAGE.format(
        name=config.client_name,
        vpn_type=config.vpn_type.value,
        mini_app_url=ctx.mini_app_url or "—",
    )
    result: dict[str, Any] = {
        "type": "article",
        "id": f"cfg:{config.id}",
        "title": i18n.INLINE_CONFIG_TITLE.format(name=config.client_name, vpn_type=config.vpn_type.value),
        "description": i18n.INLINE_CONFIG_ARTICLE_DESC.format(vpn_type=config.vpn_type.value),
        "input_message_content": {
            "message_text": message,
            "parse_mode": "HTML",
        },
    }
    if ctx.mini_app_url:
        result["reply_markup"] = {
            "inline_keyboard": [[{"text": i18n.BTN_OPEN_MINI_APP_CONFIG, "url": ctx.mini_app_url}]],
        }
    return result


def _build_config_results(ctx: BotContext, config: VpnConfig) -> list[dict[str, Any]]:
    adapter = get_active_adapter(ctx.db)
    raw_files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    enriched = enrich_profile_files(config.client_name, raw_files)
    if not enriched:
        return [_config_article_fallback(ctx, config)]

    primary = enriched[0]
    document = _config_document_result(ctx, config, primary)
    if document is not None:
        return [document]
    return [_config_article_fallback(ctx, config)]


def build_inline_results(ctx: BotContext, query: str) -> list[dict[str, Any]]:
    if ctx.user is None:
        return [_unlinked_article()]

    normalized = (query or "").strip().lower()
    results: list[dict[str, Any]] = []

    mini_app = _mini_app_article(ctx)
    if mini_app is not None and (not normalized or normalized in _MINI_APP_QUERY_HINTS):
        results.append(mini_app)

    configs = search_user_configs(ctx.db, ctx.user, query, limit=_MAX_INLINE_RESULTS)
    for config in configs:
        results.extend(_build_config_results(ctx, config))
        if len(results) >= _MAX_INLINE_RESULTS:
            break

    if not results:
        results.append(
            {
                "type": "article",
                "id": "empty",
                "title": i18n.INLINE_EMPTY_TITLE,
                "description": i18n.INLINE_EMPTY_DESC.format(query=query.strip() or "—"),
                "input_message_content": {
                    "message_text": i18n.INLINE_EMPTY_MESSAGE.format(query=query.strip() or "—"),
                    "parse_mode": "HTML",
                },
            }
        )
    return results[:_MAX_INLINE_RESULTS]


async def handle_inline_query(ctx: BotContext, inline_query: dict[str, Any]) -> None:
    query_id = str(inline_query.get("id") or "")
    if not query_id:
        return

    query = str(inline_query.get("query") or "")
    cache_key = inline_results_cache_key(ctx.telegram_user_id, query)

    def _fetch() -> list[dict[str, Any]]:
        return build_inline_results(ctx, query)

    results = get_cached_inline_results(cache_key, INLINE_RESULTS_TTL_SECONDS, _fetch)
    ok = await answer_inline_query(
        ctx.bot_token,
        query_id,
        results,
        cache_time=INLINE_RESULTS_TTL_SECONDS,
        is_personal=True,
    )
    if not ok:
        logger.warning("answerInlineQuery failed for query=%r user=%s", query, ctx.telegram_user_id)


async def handle_chosen_inline_result(ctx: BotContext, chosen: dict[str, Any]) -> None:
    result_id = str(chosen.get("result_id") or "")
    if not result_id.startswith("cfg:") or ctx.user is None:
        return

    parts = result_id.split(":", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        return
    config_id = int(parts[1])

    from app.services.telegram_bot_handlers.configs import _get_accessible_config
    from app.services.telegram_config_send import send_config_for_user

    config = await _get_accessible_config(ctx, config_id)
    if config is None:
        return

    from_user = chosen.get("from") or {}
    chat_id = from_user.get("id")
    if not chat_id:
        return

    path = parts[2] if len(parts) > 2 and parts[2] else None
    send_config_for_user(
        ctx.db,
        config,
        ctx.user,
        bot_token=ctx.bot_token,
        path=path,
        chat_id_override=chat_id,
        run_async=True,
    )
