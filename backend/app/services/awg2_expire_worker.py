"""Periodic AWG2 expiry reconciliation against on-disk state."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Node, VpnConfig, VpnType
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.client_sync import maybe_replicate_delete, purge_ha_shadow_configs
from app.services.node_sync.groups import find_sync_group_for_primary

logger = logging.getLogger(__name__)
AWG2_EXPIRE_INTERVAL_SECONDS = 60
# Panel-set and node-set expiry differ by sub-second rounding; ignore drift below this.
_EXPIRY_DRIFT_TOLERANCE = timedelta(seconds=1)


def _node_expiry_map(adapter) -> dict[str, datetime]:
    """Read `expiry.tsv` from the node; treat any failure as "no upstream data"."""
    try:
        data = adapter.awg2_expiry_map()
    except Exception as exc:  # noqa: BLE001 - tsv reconcile is best-effort
        logger.debug("awg2_expire: expiry map unavailable: %s", exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(name): value
        for name, value in data.items()
        if isinstance(value, datetime)
    }


def _delete_config_row(db: Session, node: Node, config: VpnConfig) -> None:
    """Delete a config row through the same HA-aware path as `DELETE /api/configs/{id}`."""
    if find_sync_group_for_primary(db, node.id):
        maybe_replicate_delete(db, node_id=node.id, primary_config=config)
    purge_ha_shadow_configs(db, config.id)
    db.delete(config)


def _reconcile_node(db: Session, node: Node) -> tuple[int, int, int]:
    adapter = get_adapter_for_node(node)
    adapter.awg2_expire_check()
    on_disk = {name.strip() for name in adapter.list_amneziawg2_clients() if name and name.strip()}
    upstream_expiry = _node_expiry_map(adapter)
    now = datetime.utcnow()
    deleted_cli = 0
    deleted_db = 0
    refreshed = 0

    configs = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node.id,
            VpnConfig.vpn_type == VpnType.amneziawg2,
        )
        .all()
    )
    for config in configs:
        upstream = upstream_expiry.get(config.client_name)
        if upstream is not None and (
            config.expires_at is None
            or abs(config.expires_at - upstream) > _EXPIRY_DRIFT_TOLERANCE
        ):
            config.expires_at = upstream
            refreshed += 1

        # Absence from disk alone is never a reason to delete a panel row: a restored older
        # backup would otherwise wipe every client created after the backup was taken.
        if config.expires_at is None or config.expires_at > now:
            continue

        if config.client_name in on_disk:
            adapter.awg2_delete_client(config.client_name)
            deleted_cli += 1
            on_disk.discard(config.client_name)
        _delete_config_row(db, node, config)
        deleted_db += 1
    return deleted_cli, deleted_db, refreshed


def run_awg2_expire_once(db_session_factory: Callable[[], Session] = SessionLocal) -> dict[str, int]:
    db = db_session_factory()
    try:
        node_ids = [
            row[0]
            for row in db.query(VpnConfig.node_id)
            .filter(VpnConfig.vpn_type == VpnType.amneziawg2)
            .distinct()
            .all()
        ]
        nodes_processed = 0
        nodes_failed = 0
        deleted_cli = 0
        deleted_db = 0
        refreshed = 0
        for node_id in node_ids:
            node = db.get(Node, node_id)
            if node is None:
                continue
            # One unreachable or un-provisioned node must not abort expiry for the others.
            try:
                cli_count, db_count, refresh_count = _reconcile_node(db, node)
                db.commit()
            except Exception:
                db.rollback()
                nodes_failed += 1
                logger.warning(
                    "awg2_expire: node %s (%s) reconcile failed",
                    node_id,
                    getattr(node, "name", "?"),
                    exc_info=True,
                )
                continue
            nodes_processed += 1
            deleted_cli += cli_count
            deleted_db += db_count
            refreshed += refresh_count
        return {
            "nodes_processed": nodes_processed,
            "nodes_failed": nodes_failed,
            "deleted_cli": deleted_cli,
            "deleted_db": deleted_db,
            "expiry_refreshed": refreshed,
        }
    finally:
        db.close()


async def run_awg2_expire_loop() -> None:
    while True:
        try:
            result = await asyncio.to_thread(run_awg2_expire_once, SessionLocal)
            if result["deleted_cli"] or result["deleted_db"] or result["expiry_refreshed"]:
                logger.info(
                    "awg2_expire: nodes=%s failed=%s deleted_cli=%s deleted_db=%s refreshed=%s",
                    result["nodes_processed"],
                    result["nodes_failed"],
                    result["deleted_cli"],
                    result["deleted_db"],
                    result["expiry_refreshed"],
                )
        except Exception:
            logger.exception("awg2_expire failed")
        await asyncio.sleep(AWG2_EXPIRE_INTERVAL_SECONDS)
