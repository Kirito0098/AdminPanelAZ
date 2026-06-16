"""Background worker that periodically evaluates custom alert rules."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.services.alert_rules import run_alert_rules_tick

logger = logging.getLogger(__name__)


async def run_alert_rules_loop() -> None:
    settings = get_settings()
    if not settings.alert_rules_enabled:
        return

    interval = max(30, int(settings.alert_rules_check_interval_seconds or 60))
    while True:
        try:
            await asyncio.sleep(interval)
            result = await asyncio.to_thread(run_alert_rules_tick)
            if result.get("triggered"):
                logger.info(
                    "Alert rules: %d/%d rule(s) triggered",
                    result.get("triggered", 0),
                    result.get("evaluated", 0),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Alert rules worker error: %s", exc)
