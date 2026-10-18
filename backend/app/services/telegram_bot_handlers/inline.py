"""Telegram bot inline query — search configs; files only via private DM."""

from __future__ import annotations

import logging
from typing import Any

from app.models import VpnConfig
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
_PRIVATE_CHAT_TYPES = frozenset({"sender"})


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


def _private_only_article() -> dict[str, Any]:
    return {
        "type": "article",
        "id": "private_only",
        "title": i18n.INLINE_PRIVATE_ONLY_TITLE,
        "description": i18n.INLINE_PRIVATE_ONLY_DESC,
        "input_message_content": {
            "message_text": i18n.INLINE_PRIVATE_ONLY_MESSAGE,
            "parse_mode": "HTML",
        },
    }


def _config_article(ctx: BotContext, config: VpnConfig) -> dict[str, Any]:
    message = i18n.INLINE_CONFIG_MESSAGE.format(
        name=config.client_name,
        vpn_type=config.vpn_type.value,
        mini_app_url=ctx.mini_app_url or "—",
    )
    return {
        "type": "article",
        "id": f"cfg:{config.id}",
        "title": i18n.INLINE_CONFIG_TITLE.format(name=config.client_name, vpn_type=config.vpn_type.value),
        "description": i18n.INLINE_CONFIG_ARTICLE_DESC.format(vpn_type=config.vpn_type.value),
        "input_message_content": {
            "message_text": message,
            "parse_mode": "HTML",
        },
    }


def build_inline_results(
    ctx: BotContext,
    query: str,
    *,
    chat_type: str | None = None,
) -> list[dict[str, Any]]:
    """Build inline results. Config articles only in the user's private chat with the bot (`sender`)."""
    normalized_chat = (chat_type or "").strip().lower()
    if normalized_chat not in _PRIVATE_CHAT_TYPES:
        return [_private_only_article()]

    if ctx.user is None:
        return [_unlinked_article()]

    normalized = (query or "").strip().lower()
    results: list[dict[str, Any]] = []

    mini_app = _mini_app_article(ctx)
    if mini_app is not None and (not normalized or normalized in _MINI_APP_QUERY_HINTS):
        results.append(mini_app)

    configs = search_user_configs(ctx.db, ctx.user, query, limit=_MAX_INLINE_RESULTS)
    for config in configs:
        results.append(_config_article(ctx, config))
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
    chat_type = str(inline_query.get("chat_type") or "") or None
    # Cache only private (sender) results so a group query never reuses config articles.
    cache_key = inline_results_cache_key(ctx.telegram_user_id, f"{chat_type or ''}|{query}")

    def _fetch() -> list[dict[str, Any]]:
        return build_inline_results(ctx, query, chat_type=chat_type)

    results = get_cached_inline_results(cache_key, INLINE_RESULTS_TTL_SECONDS, _fetch)

    switch_pm_text = None
    switch_pm_parameter = None
    if results and results[0].get("id") == "private_only":
        switch_pm_text = i18n.INLINE_PRIVATE_ONLY_BUTTON
        switch_pm_parameter = "start"

    ok = await answer_inline_query(
        ctx.bot_token,
        query_id,
        results,
        cache_time=INLINE_RESULTS_TTL_SECONDS,
        is_personal=True,
        switch_pm_text=switch_pm_text,
        switch_pm_parameter=switch_pm_parameter,
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

    from app.services.telegram import send_tg_message
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
    sent, err = send_config_for_user(
        ctx.db,
        config,
        ctx.user,
        bot_token=ctx.bot_token,
        path=path,
        chat_id_override=chat_id,
        run_async=False,
    )
    if err or sent == 0:
        send_tg_message(
            ctx.bot_token,
            str(chat_id),
            err or "Не удалось отправить конфиг в Telegram",
            run_async=False,
        )
