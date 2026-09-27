"""Background worker for webhook delivery retries."""

from __future__ import annotations

import asyncio
import logging

from app.services.event_webhooks import event_webhook_service
from app.services.background_gate import run_background_step

logger = logging.getLogger(__name__)


async def run_webhook_delivery_loop() -> None:
    while True:
        try:
            await run_background_step(event_webhook_service.process_pending_deliveries)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Webhook delivery loop failed")
        await asyncio.sleep(30)
