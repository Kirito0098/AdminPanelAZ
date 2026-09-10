"""Periodic access-until expiry reconciliation."""

from __future__ import annotations

import asyncio
import logging

from app.database import SessionLocal
from app.services.access_until import apply_due_access_blocks

logger = logging.getLogger(__name__)
ACCESS_EXPIRY_INTERVAL_SECONDS = 60


def _run_once() -> dict[str, int]:
    db = SessionLocal()
    try:
        return apply_due_access_blocks(db)
    finally:
        db.close()


async def run_access_expiry_loop() -> None:
    while True:
        try:
            result = await asyncio.to_thread(_run_once)
            if result.get("blocked") or result.get("errors"):
                logger.info(
                    "access_expiry: blocked=%s openvpn=%s wireguard=%s awg2=%s errors=%s rows_due=%s",
                    result.get("blocked", 0),
                    result.get("openvpn", 0),
                    result.get("wireguard", 0),
                    result.get("amneziawg2", 0),
                    result.get("errors", 0),
                    result.get("rows_due", 0),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("access_expiry failed")
        await asyncio.sleep(ACCESS_EXPIRY_INTERVAL_SECONDS)
