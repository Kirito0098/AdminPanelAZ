"""Background worker that periodically evaluates custom alert rules."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.services.alert_rules import run_alert_rules_tick

logger = logging.getLogger(__name__)


def _is_alert_rules_runtime_enabled() -> bool:
    """Runtime gate — ALERT_RULES_ENABLED + telegram can flip without restart."""
    settings = get_settings()
    if not settings.alert_rules_enabled:
        return False
    from app.services.feature_guards import get_feature_service

    return get_feature_service().is_enabled("telegram")


async def run_alert_rules_loop() -> None:
    """Alert rules loop — re-checks enable flags each tick."""
    while True:
        settings = get_settings()
        interval = max(30, int(settings.alert_rules_check_interval_seconds or 60))
        try:
            await asyncio.sleep(interval)
            if not _is_alert_rules_runtime_enabled():
                logger.debug("alert_rules skipped — disabled or telegram off")
                continue
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
