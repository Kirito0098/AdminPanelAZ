"""Long-poll getUpdates through the relay node when the panel cannot take webhooks."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.database import SessionLocal
from app.routers.telegram_webhook import _handle_update
from app.services.app_setting_store import _get_setting, _set_setting
from app.services.background_gate import run_background_step
from app.services.telegram_api import ALLOWED_UPDATES
from app.services.telegram_bot_loop import run_on_bot_loop
from app.services.telegram_transport import RELAY_NODES_SETTING, bot_api_post, last_relay_node_name
from app.services.telegram_update_dedup import claim_telegram_update

logger = logging.getLogger(__name__)

IDLE_SECONDS = 15
ERROR_PAUSE_SECONDS = 10
LONG_POLL_SECONDS = 25


def _telegram_module_enabled() -> bool:
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled("telegram")


def _polling_config() -> tuple[str, str] | None:
    if not _telegram_module_enabled():
        return None
    with SessionLocal() as db:
        token = _get_setting(db, "telegram_bot_token")
        if not token or not _get_setting(db, RELAY_NODES_SETTING):
            return None
        if _get_setting(db, "telegram_bot_interactive_enabled", "false") != "true":
            return None
        return token, _get_setting(db, "telegram_mini_app_url")


def _record(**values: str) -> None:
    with SessionLocal() as db:
        for key, value in values.items():
            _set_setting(db, key, value)
        db.commit()


async def poll_once(offset: int) -> int:
    config = await run_background_step(_polling_config)
    if config is None:
        await asyncio.sleep(IDLE_SECONDS)
        return offset
    token, mini_app_url = config
    data = await bot_api_post(
        token,
        "getUpdates",
        json={"offset": offset, "timeout": LONG_POLL_SECONDS, "allowed_updates": ALLOWED_UPDATES},
        timeout=LONG_POLL_SECONDS + 15,
    )
    if not data.get("ok"):
        raise RuntimeError(str(data.get("description") or "getUpdates failed"))
    for update in data.get("result") or []:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            offset = max(offset, update_id + 1)
        with SessionLocal() as db:
            if not claim_telegram_update(db, update_id):
                continue
        try:
            await run_on_bot_loop(_handle_update(update, mini_app_url=mini_app_url))
        except Exception:
            logger.exception("Telegram update %s handling failed", update_id)
    await run_background_step(
        _record,
        telegram_relay_last_ok_at=datetime.now(timezone.utc).isoformat(),
        telegram_relay_last_error="",
        telegram_relay_last_node=last_relay_node_name(),
    )
    return offset


async def run_telegram_polling_loop() -> None:
    offset = 0
    while True:
        try:
            offset = await poll_once(offset)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Telegram polling through relay node failed: %s", exc)
            await run_background_step(_record, telegram_relay_last_error=str(exc)[:500])
            await asyncio.sleep(ERROR_PAUSE_SECONDS)
