"""Scheduled Cloudflare Real IP auto-refresh worker."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.database import SessionLocal
from app.services.cloudflare_proxy_settings import get_cloudflare_proxy_state, refresh_cloudflare_ips

logger = logging.getLogger(__name__)

SLEEP_SECONDS = 3600


def should_run_interval(
    last_success_raw: str,
    interval_days: int,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True when the refresh interval has elapsed since the last success."""
    if not last_success_raw:
        return True
    try:
        last = datetime.fromisoformat(last_success_raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    elapsed = (current - last).total_seconds()
    return elapsed >= max(1, int(interval_days or 1)) * 86400


def should_refresh_cloudflare_ips(
    *,
    enabled: bool,
    auto_update: bool,
    interval_days: int,
    last_success_at: str | None,
    now: datetime | None = None,
) -> bool:
    """Pure skip logic for the scheduler loop."""
    if not enabled:
        return False
    if not auto_update:
        return False
    return should_run_interval(last_success_at or "", interval_days, now=now)


async def run_cloudflare_ips_scheduler_loop() -> None:
    """Background loop: check hourly if Cloudflare IPs auto-refresh should run."""
    while True:
        try:
            await asyncio.sleep(SLEEP_SECONDS)
            db = SessionLocal()
            try:
                state = get_cloudflare_proxy_state(db)
                if not should_refresh_cloudflare_ips(
                    enabled=state["enabled"],
                    auto_update=state["auto_update"],
                    interval_days=state["interval_days"],
                    last_success_at=state["last_success_at"],
                ):
                    continue
                result = refresh_cloudflare_ips(db)
                if result.get("success"):
                    logger.info(
                        "Cloudflare IPs auto-refresh: %s",
                        result.get("message", "ok"),
                    )
                else:
                    logger.warning(
                        "Cloudflare IPs auto-refresh failed: %s",
                        result.get("error"),
                    )
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Cloudflare IPs scheduler error: %s", exc)
