"""Full push: backup primary → restore all replicas."""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import Node, NodeSyncGroup, SyncStatus, User, UserRole
from app.services.config_import import import_clients_from_disk
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.groups import (
    is_auto_sync_enabled,
    parse_replica_node_ids,
    validate_sync_group_payload,
)
from app.services.node_sync.manual_link import link_primary_configs_to_group
from app.services.node_sync.openvpn_restart import restart_all_openvpn_servers
from app.services.node_sync.verify import verify_sync_group
from app.services.policy_import import copy_access_policies_from_node
from app.services.traffic.collector import collect_traffic_snapshot_for_node

logger = logging.getLogger(__name__)

# Hosts live in each node's `setup` (OPENVPN_HOST / WIREGUARD_HOST) and are NOT part of
# the client.sh 8 backup archive, so Push full must copy them from the primary explicitly.
HOST_SETTING_KEYS = ("openvpn_host", "wireguard_host")


def _read_backup_bytes(primary_adapter, backup_info: dict[str, str]) -> bytes:
    archive_path = backup_info.get("archive_path") or ""
    archive_name = backup_info.get("archive_name") or os.path.basename(archive_path)
    return primary_adapter.download_antizapret_backup(archive_name)


def read_primary_host_settings(primary_adapter) -> dict[str, str]:
    """Return non-empty OPENVPN_HOST / WIREGUARD_HOST from the primary's setup."""
    try:
        settings = primary_adapter.get_antizapret_settings()
    except Exception as exc:
        logger.warning("Push full: failed to read primary host settings: %s", exc)
        return {}
    if not isinstance(settings, dict):
        return {}
    hosts: dict[str, str] = {}
    for key in HOST_SETTING_KEYS:
        value = str(settings.get(key, "") or "").strip()
        if value:
            hosts[key] = value
    return hosts


def run_push_full(
    db: Session,
    group: NodeSyncGroup,
    *,
    progress_callback: Callable[[int, str, str | None], None] | None = None,
    auto_verify: bool = True,
) -> dict[str, Any]:
    def progress(percent: int, stage: str, message: str | None = None) -> None:
        if progress_callback:
            progress_callback(percent, stage, message)

    errors = validate_sync_group_payload(
        db,
        primary_node_id=group.primary_node_id,
        replica_node_ids=parse_replica_node_ids(group.replica_node_ids),
        exclude_group_id=group.id,
    )
    if errors:
        raise RuntimeError("; ".join(errors))

    group.sync_status = SyncStatus.pending
    group.last_sync_error = None
    db.commit()

    progress(10, "Создание бэкапа на primary…")
    primary_node = db.get(Node, group.primary_node_id)
    primary_adapter = get_adapter_for_node(primary_node)
    backup_info = primary_adapter.create_antizapret_backup()

    progress(30, "Чтение архива…")
    archive_bytes = _read_backup_bytes(primary_adapter, backup_info)
    archive_name = backup_info.get("archive_name") or "backup.tar.gz"

    primary_host_settings = read_primary_host_settings(primary_adapter)

    replica_ids = parse_replica_node_ids(group.replica_node_ids)
    restored: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    host_copy: list[dict[str, Any]] = []
    openvpn_restart: list[dict[str, Any]] = []
    admin = db.query(User).filter(User.role == UserRole.admin).first()

    for index, replica_id in enumerate(replica_ids):
        percent = 40 + int((index / max(len(replica_ids), 1)) * 45)
        replica_node = db.get(Node, replica_id)
        replica_name = replica_node.name if replica_node else str(replica_id)
        progress(percent, f"Restore на {replica_name}…")

        replica_adapter = get_adapter_for_node(replica_node)
        # Copy primary hosts into the replica's setup BEFORE restore, so the restore's
        # client.sh 7 (recreate_profiles) regenerates client profiles with the right host.
        if primary_host_settings:
            try:
                replica_adapter.update_antizapret_settings(dict(primary_host_settings))
                host_copy.append(
                    {
                        "node_id": replica_id,
                        "node_name": replica_name,
                        "hosts": dict(primary_host_settings),
                    }
                )
            except Exception as exc:
                logger.warning(
                    "Push full: failed to copy host settings to %s: %s", replica_name, exc
                )
                host_copy.append(
                    {"node_id": replica_id, "node_name": replica_name, "error": str(exc)}
                )
        try:
            if isinstance(replica_adapter, LocalNodeAdapter):
                with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                    tmp.write(archive_bytes)
                    tmp_path = tmp.name
                try:
                    result = replica_adapter.restore_antizapret_backup(tmp_path)
                finally:
                    os.unlink(tmp_path)
            else:
                result = replica_adapter.restore_antizapret_backup(archive_bytes, archive_name)
            restored.append({"node_id": replica_id, "node_name": replica_name, "result": result})

            progress(percent, f"Перезапуск OpenVPN на {replica_name}…")
            restart_result = restart_all_openvpn_servers(replica_adapter)
            openvpn_restart.append(
                {
                    "node_id": replica_id,
                    "node_name": replica_name,
                    **restart_result,
                }
            )
            if restart_result.get("failed"):
                logger.warning(
                    "Push full: OpenVPN restart partial failure on %s: %s",
                    replica_name,
                    restart_result.get("failed"),
                )

            if admin and replica_node and primary_node:
                import_clients_from_disk(db, replica_node, admin.id)
                copy_access_policies_from_node(db, primary_node, replica_node)
                try:
                    collect_traffic_snapshot_for_node(db, replica_node.id)
                except Exception as exc:
                    logger.warning(
                        "Traffic snapshot after push full failed on %s: %s",
                        replica_name,
                        exc,
                    )
        except Exception as exc:
            failed.append({"node_id": replica_id, "node_name": replica_name, "error": str(exc)})
            group.sync_status = SyncStatus.failed
            group.last_sync_error = str(exc)
            group.last_sync_at = datetime.utcnow()
            db.commit()
            progress(100, "Push full завершился с ошибкой")
            return {
                "success": False,
                "message": f"Restore failed on {replica_name}: {exc}",
                "backup": backup_info,
                "restored": restored,
                "failed": failed,
                "host_copy": host_copy,
                "openvpn_restart": openvpn_restart,
            }

    group.sync_status = SyncStatus.synced
    group.last_sync_at = datetime.utcnow()
    group.last_sync_error = None
    if not is_auto_sync_enabled(group):
        link_primary_configs_to_group(db, group)
    db.commit()

    verify_result = None
    if auto_verify:
        progress(90, "Verify после sync…")
        verify_result = verify_sync_group(db, group)

    progress(100, "Push full завершён")
    restart_names = [item.get("node_name") for item in openvpn_restart if item.get("restarted")]
    message = "Полная синхронизация завершена"
    if restart_names:
        message += f". OpenVPN перезапущен на: {', '.join(str(n) for n in restart_names if n)}"
    return {
        "success": True,
        "message": message,
        "backup": backup_info,
        "restored": restored,
        "failed": failed,
        "host_copy": host_copy,
        "openvpn_restart": openvpn_restart,
        "verify": verify_result,
    }
