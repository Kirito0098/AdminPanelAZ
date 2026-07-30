"""Background sync of real OpenVPN certificate expiry dates from nodes into the DB."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.models import Node, VpnConfig, VpnType
from app.services.node_manager import get_adapter_for_node
from app.services.openvpn_cert import resolve_openvpn_cert_not_after, to_naive_utc
from app.services.openvpn_pki import load_cert_expiry_map

logger = logging.getLogger(__name__)
settings = get_settings()

# Give the app and node agents time to come up before the first pass.
INITIAL_DELAY_SECONDS = 15


def _sync_node(db, node: Node) -> int:
    configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node.id,
            VpnConfig.vpn_type == VpnType.openvpn,
        )
        .all()
    )
    if not configs:
        return 0

    adapter = get_adapter_for_node(node)
    # One remote round-trip (GET /openvpn/certs/expiry or index.txt) covers every client.
    try:
        expiry_by_cn = load_cert_expiry_map(adapter)
    except Exception:
        logger.exception(
            "cert_sync: failed to load expiry map from node id=%s name=%s local=%s",
            node.id,
            node.name,
            bool(node.is_local),
        )
        expiry_by_cn = {}

    updated = 0
    missing_fallback = 0
    for config in configs:
        not_after = expiry_by_cn.get(config.client_name)
        if not_after is None:
            # Rare: CN not in index (or map fetch failed) — read that client's .ovpn once.
            not_after = resolve_openvpn_cert_not_after(adapter, config.client_name)
            if not_after is not None:
                missing_fallback += 1
        if not_after is None:
            continue
        naive = to_naive_utc(not_after)
        if config.cert_expires_at != naive:
            config.cert_expires_at = naive
            updated += 1

    if missing_fallback:
        logger.info(
            "cert_sync: node %s used .ovpn fallback for %s client(s)",
            node.name,
            missing_fallback,
        )
    return updated


def sync_cert_expiry(db) -> int:
    """Refresh cert_expires_at for OpenVPN configs on every node (local + remote). Returns update count."""
    updated = 0
    for node in db.query(Node).all():
        try:
            count = _sync_node(db, node)
            updated += count
            if count:
                logger.info(
                    "cert_sync: node %s refreshed %s config(s) (local=%s)",
                    node.name,
                    count,
                    bool(node.is_local),
                )
        except Exception:
            logger.exception("cert_sync: skip node id=%s name=%s", node.id, node.name)
    if updated:
        db.commit()
    return updated


async def run_cert_sync_loop() -> None:
    interval = max(60, int(settings.cert_sync_interval_seconds))
    await asyncio.sleep(INITIAL_DELAY_SECONDS)
    while True:
        db = SessionLocal()
        try:
            count = sync_cert_expiry(db)
            if count:
                logger.info("cert_sync: refreshed cert_expires_at for %s configs total", count)
        except Exception:
            logger.exception("cert_sync failed")
        finally:
            db.close()
        await asyncio.sleep(interval)
