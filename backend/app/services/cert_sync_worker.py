"""Background sync of OpenVPN certificate expiry days from remote nodes into the DB."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.models import VpnConfig, VpnType
from app.services.node_manager import get_active_node, get_adapter_for_node
from app.services.openvpn_cert import resolve_openvpn_cert_days_remaining

logger = logging.getLogger(__name__)
settings = get_settings()


def sync_missing_cert_expire_days(db) -> int:
    """Fill cert_expire_days for OpenVPN configs missing it on the active node. Returns update count."""
    try:
        node = get_active_node(db)
    except Exception:
        return 0

    adapter = get_adapter_for_node(node)
    configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node.id,
            VpnConfig.vpn_type == VpnType.openvpn,
            VpnConfig.cert_expire_days.is_(None),
        )
        .all()
    )
    if not configs:
        return 0

    updated = 0
    for config in configs:
        days = resolve_openvpn_cert_days_remaining(adapter, config.client_name)
        if days is not None:
            config.cert_expire_days = days
            updated += 1

    if updated:
        db.commit()
    return updated


async def run_cert_sync_loop() -> None:
    interval = max(60, int(settings.cert_sync_interval_seconds))
    while True:
        await asyncio.sleep(interval)
        db = SessionLocal()
        try:
            count = sync_missing_cert_expire_days(db)
            if count:
                logger.info("cert_sync: updated cert_expire_days for %s configs", count)
        except Exception:
            logger.exception("cert_sync failed")
        finally:
            db.close()
