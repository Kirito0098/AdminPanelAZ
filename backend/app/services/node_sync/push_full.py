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
from app.services.node_adapter import LocalNodeAdapter
from app.services.node_manager import get_adapter_for_node
from app.services.node_sync.groups import (
    is_auto_sync_enabled,
    parse_replica_node_ids,
    validate_sync_group_payload,
)
from app.services.node_sync.manual_link import link_primary_configs_to_group
from app.services.node_sync.openvpn_restart import restart_all_openvpn_servers
from app.services.node_sync.shadow_link import format_shadow_link_warning, link_shadow_configs_for_group
from app.services.node_sync.verify import verify_sync_group
from app.services.node_sync.vpn_state_sync import (
    copy_openvpn_profiles_from_primary,
    prune_replica_vpn_clients,
)
from app.services.policy_import import copy_access_policies_from_node
from app.services.traffic.collector import collect_traffic_snapshot_for_node

logger = logging.getLogger(__name__)

HOST_SETTING_KEYS = ("openvpn_host", "wireguard_host")


def _read_backup_bytes(primary_adapter, backup_info: dict[str, str]) -> bytes:
    archive_path = backup_info.get("archive_path") or ""
    archive_name = backup_info.get("archive_name") or os.path.basename(archive_path)
    return primary_adapter.download_antizapret_backup(archive_name)


def read_primary_host_settings(primary_adapter) -> dict[str, str]:
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


def _restore_ha_replica(replica_adapter, archive_bytes: bytes, archive_name: str, tmp_path: str | None) -> dict[str, str]:
    if isinstance(replica_adapter, LocalNodeAdapter):
        return replica_adapter.restore_antizapret_backup(tmp_path, ha_replica=True)
    return replica_adapter.restore_antizapret_backup(archive_bytes, archive_name, ha_replica=True)


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
    openvpn_profile_copy: list[dict[str, Any]] = []
    replica_prune: list[dict[str, Any]] = []
    admin = db.query(User).filter(User.role == UserRole.admin).first()

    for index, replica_id in enumerate(replica_ids):
        percent = 40 + int((index / max(len(replica_ids), 1)) * 45)
        replica_node = db.get(Node, replica_id)
        replica_name = replica_node.name if replica_node else str(replica_id)
        progress(percent, f"HA restore на {replica_name}…")

        replica_adapter = get_adapter_for_node(replica_node)
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
                    result = _restore_ha_replica(replica_adapter, archive_bytes, archive_name, tmp_path)
                finally:
                    os.unlink(tmp_path)
            else:
                result = _restore_ha_replica(replica_adapter, archive_bytes, archive_name, None)

            progress(percent, f"Копия OpenVPN-профилей primary → {replica_name}…")
            copy_openvpn_profiles_from_primary(primary_adapter, replica_adapter)
            openvpn_profile_copy.append({"node_id": replica_id, "node_name": replica_name, "success": True})

            progress(percent, f"Очистка лишних VPN-клиентов на {replica_name}…")
            prune_result = prune_replica_vpn_clients(primary_adapter, replica_adapter)
            replica_prune.append({"node_id": replica_id, "node_name": replica_name, **prune_result})
            if not prune_result.get("success"):
                raise RuntimeError(
                    "; ".join(str(item) for item in prune_result.get("errors") or [])
                    or "prune failed"
                )

            progress(percent, f"Перезапуск OpenVPN на {replica_name}…")
            restart_result = restart_all_openvpn_servers(replica_adapter)
            openvpn_restart.append(
                {
                    "node_id": replica_id,
                    "node_name": replica_name,
                    **restart_result,
                }
            )
            if not restart_result.get("success"):
                failed_units = restart_result.get("failed") or []
                raise RuntimeError(
                    "; ".join(
                        str(entry.get("error") or entry.get("unit") or entry)
                        for entry in failed_units
                    )
                    or "OpenVPN restart failed"
                )

            progress(percent, f"Применение WireGuard на {replica_name}…")
            wg_runtime = replica_adapter.apply_wireguard_runtime()
            if not wg_runtime.get("success"):
                wg_errors = wg_runtime.get("errors") or []
                raise RuntimeError(
                    "; ".join(
                        str(entry.get("stderr") or entry.get("error") or entry)
                        for entry in wg_errors
                    )
                    or "WireGuard runtime apply failed"
                )

            restored.append({"node_id": replica_id, "node_name": replica_name, "result": result})

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
            logger.warning("Push full: replica sync failed on %s: %s", replica_name, exc)
            if openvpn_profile_copy and openvpn_profile_copy[-1].get("node_id") == replica_id:
                if openvpn_profile_copy[-1].get("success"):
                    openvpn_profile_copy[-1] = {
                        "node_id": replica_id,
                        "node_name": replica_name,
                        "error": str(exc),
                    }

    group.last_sync_at = datetime.utcnow()
    shadow_link_result = None
    verify_result = None
    all_restored = not failed and len(restored) == len(replica_ids)

    if all_restored:
        if is_auto_sync_enabled(group):
            shadow_link_result = link_shadow_configs_for_group(db, group)
        else:
            link_primary_configs_to_group(db, group)
    db.commit()

    if auto_verify and all_restored:
        progress(90, "Verify после sync…")
        verify_result = verify_sync_group(db, group)

    shadow_warning = format_shadow_link_warning(shadow_link_result) if shadow_link_result else None
    verify_not_ready = isinstance(verify_result, dict) and verify_result.get("ready") is False

    if failed:
        group.sync_status = SyncStatus.failed
        error_parts = [f"{item.get('node_name')}: {item.get('error')}" for item in failed]
        group.last_sync_error = "; ".join(error_parts)
        success = False
        message = f"Push full: ошибки на {len(failed)} из {len(replica_ids)} реплик"
    elif shadow_warning or verify_not_ready:
        group.sync_status = SyncStatus.failed
        group.last_sync_error = shadow_warning or str(verify_result.get("summary") or "Verify не готов")
        success = False
        message = "Push full завершён с предупреждениями — см. last_sync_error"
    else:
        group.sync_status = SyncStatus.synced
        group.last_sync_error = None
        success = True
        message = "Полная синхронизация завершена"

    db.commit()
    progress(100, "Push full завершён" if success else "Push full завершился с ошибкой")
    restart_names = [item.get("node_name") for item in openvpn_restart if item.get("restarted")]
    if success and restart_names:
        message += f". OpenVPN перезапущен на: {', '.join(str(n) for n in restart_names if n)}"
    return {
        "success": success,
        "message": message,
        "backup": backup_info,
        "restored": restored,
        "failed": failed,
        "host_copy": host_copy,
        "openvpn_restart": openvpn_restart,
        "openvpn_profile_copy": openvpn_profile_copy,
        "replica_prune": replica_prune,
        "shadow_link": shadow_link_result,
        "verify": verify_result,
    }
