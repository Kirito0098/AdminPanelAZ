#!/usr/bin/env python3
"""Nightly CIDR database refresh script (cron-compatible).

Downloads fresh CIDR data from all providers into SQLite on the controller.
Does NOT regenerate ips/list/*.txt — use API generate or UI after refresh.
"""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [cidr-db-refresh] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    db = SessionLocal()
    svc = CidrDbUpdaterService(db=db)
    try:
        logger.info("Starting CIDR DB refresh (cron)")
        result = svc.refresh_all_providers(triggered_by="cron")
        logger.info(
            "Done: status=%s updated=%d failed=%d total_cidrs=%d",
            result.get("status"),
            result.get("providers_updated", 0),
            result.get("providers_failed", 0),
            result.get("total_cidrs", 0),
        )
        return 0 if result.get("status") in ("ok", "partial") else 1
    finally:
        svc.close()
        db.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        logger.exception("CIDR DB refresh failed: %s", exc)
        sys.exit(1)
