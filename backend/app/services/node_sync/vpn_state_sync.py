"""HA auto-sync: copy VPN crypto state (WireGuard conf + OpenVPN easyrsa3) from primary to replica."""

from __future__ import annotations

import io
import logging
import tarfile

from fastapi import HTTPException

from app.models import VpnType
from app.services.node_sync.openvpn_restart import restart_all_openvpn_servers
from app.services.openvpn_pki import validate_all_openvpn_profiles

logger = logging.getLogger(__name__)

WIREGUARD_INTERFACES = ("antizapret", "vpn")


def _error_detail(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail is not None:
        return str(detail)
    return str(exc)


def _archive_has_wireguard_profile_files(data: bytes) -> bool:
    if not data:
        return False
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            return any(
                member.isfile()
                and (
                    member.name.startswith("client/wireguard/")
                    or member.name.startswith("client/amneziawg/")
                )
                for member in archive.getmembers()
            )
    except tarfile.TarError:
        return False


def _copy_client_wireguard_profiles_from_primary(
    primary_adapter,
    replica_adapter,
    client_name: str,
) -> int:
    files = primary_adapter.get_profile_files(client_name, VpnType.wireguard)
    copied = 0
    for entry in files:
        path = entry.get("path")
        if not path:
            continue
        content = primary_adapter.read_profile_file(path)
        replica_adapter.write_profile_file(path, content)
        copied += 1
    return copied


def _copy_all_wireguard_profiles_from_primary(
    primary_adapter,
    replica_adapter,
    *,
    client_name: str | None = None,
) -> None:
    archive = primary_adapter.export_wireguard_client_profiles_archive()
    if _archive_has_wireguard_profile_files(archive):
        replica_adapter.import_wireguard_client_profiles_archive(archive)
        return

    if client_name:
        copied = _copy_client_wireguard_profiles_from_primary(
            primary_adapter,
            replica_adapter,
            client_name,
        )
        if copied:
            logger.warning(
                "HA crypto sync: primary WG profile archive empty; copied %s file(s) for client %s",
                copied,
                client_name,
            )
            return

    raise HTTPException(
        status_code=500,
        detail=(
            "На primary нет файлов профилей WireGuard/AmneziaWG для копирования на replica. "
            "Проверьте node agent и каталог client/wireguard на основном узле."
        ),
    )


def _mirror_wireguard_server_configs(primary_adapter, replica_adapter) -> None:
    """Copy WG server .conf from primary and remove extras on replica."""
    primary_files = set(primary_adapter.list_wireguard_server_config_files())
    for interface in WIREGUARD_INTERFACES:
        conf_name = f"{interface}.conf"
        if conf_name in primary_files:
            content = primary_adapter.read_wireguard_server_config(interface)
            replica_adapter.write_wireguard_server_config(interface, content)
    replica_files = set(replica_adapter.list_wireguard_server_config_files())
    for extra in sorted(replica_files - primary_files):
        replica_adapter.delete_wireguard_server_config_file(extra)


def prune_replica_vpn_clients(primary_adapter, replica_adapter) -> dict[str, object]:
    """Remove VPN clients that exist on replica but not on primary."""
    primary_ovpn = set(primary_adapter.list_openvpn_clients())
    primary_wg = set(primary_adapter.list_wireguard_clients())
    removed_ovpn: list[str] = []
    removed_wg: list[str] = []
    errors: list[str] = []

    for client_name in replica_adapter.list_openvpn_clients():
        if client_name in primary_ovpn:
            continue
        try:
            replica_adapter.delete_openvpn_client(client_name)
            removed_ovpn.append(client_name)
        except Exception as exc:
            errors.append(f"openvpn {client_name}: {_error_detail(exc)}")

    for client_name in replica_adapter.list_wireguard_clients():
        if client_name in primary_wg:
            continue
        try:
            replica_adapter.delete_wireguard_client(client_name)
            removed_wg.append(client_name)
        except Exception as exc:
            errors.append(f"wireguard {client_name}: {_error_detail(exc)}")

    return {
        "removed_ovpn": removed_ovpn,
        "removed_wg": removed_wg,
        "errors": errors,
        "success": not errors,
    }


def sync_wireguard_state_from_primary(
    primary_adapter,
    replica_adapter,
    *,
    client_name: str | None = None,
) -> None:
    """Copy WireGuard server configs and all WG/AWG profile files from primary to replica."""
    _mirror_wireguard_server_configs(primary_adapter, replica_adapter)

    runtime = replica_adapter.apply_wireguard_runtime()
    if not runtime.get("success"):
        errors = runtime.get("errors") or []
        detail = "; ".join(
            str(entry.get("stderr") or entry.get("error") or entry)
            for entry in errors
        ) or "WireGuard runtime apply failed"
        logger.warning(
            "HA crypto sync: wg syncconf partial failure on replica (configs copied): %s",
            detail,
        )

    _copy_all_wireguard_profiles_from_primary(
        primary_adapter,
        replica_adapter,
        client_name=client_name,
    )


def copy_openvpn_profiles_from_primary(primary_adapter, replica_adapter) -> None:
    """Byte-copy all .ovpn profile files from primary to replica."""
    archive = primary_adapter.export_openvpn_client_profiles_archive()
    if not archive:
        logger.warning("HA crypto sync: primary OpenVPN profile archive is empty")
        return
    replica_adapter.import_openvpn_client_profiles_archive(archive)


def sync_openvpn_pki_from_primary(primary_adapter, replica_adapter) -> None:
    """Copy OpenVPN PKI and .ovpn profiles from primary to replica (no cert re-issue)."""
    archive = primary_adapter.export_easyrsa3_archive()
    replica_adapter.import_easyrsa3_archive(archive)
    copy_openvpn_profiles_from_primary(primary_adapter, replica_adapter)

    replica_validation = validate_all_openvpn_profiles(replica_adapter)
    if not replica_validation.ready:
        logger.warning(
            "HA crypto sync: replica OpenVPN profile cert validation issues after copy: %s",
            [
                {
                    "client": issue.client_name,
                    "file": issue.filename,
                    "status": issue.status,
                    "serial": issue.serial_hex,
                }
                for issue in replica_validation.issues
            ],
        )

    restart_result = restart_all_openvpn_servers(replica_adapter)
    if not restart_result.get("success"):
        failed = restart_result.get("failed") or []
        detail = "; ".join(
            str(entry.get("error") or entry.get("unit") or entry)
            for entry in failed
        ) or "OpenVPN restart failed after PKI sync"
        raise HTTPException(status_code=500, detail=detail)


def sync_vpn_crypto_from_primary(
    primary_adapter,
    replica_adapter,
    vpn_type: VpnType,
    *,
    client_name: str | None = None,
) -> None:
    """Copy primary VPN crypto material to replica for HA failover parity."""
    if vpn_type == VpnType.openvpn:
        sync_openvpn_pki_from_primary(primary_adapter, replica_adapter)
        return
    sync_wireguard_state_from_primary(
        primary_adapter,
        replica_adapter,
        client_name=client_name,
    )


def sync_all_vpn_crypto_from_primary(primary_adapter, replica_adapter) -> None:
    """Copy both WireGuard and OpenVPN crypto state from primary to replica."""
    sync_wireguard_state_from_primary(primary_adapter, replica_adapter)
    sync_openvpn_pki_from_primary(primary_adapter, replica_adapter)


def replicate_primary_crypto_to_replicas(db, group, primary_config) -> dict[str, object]:
    """Copy VPN crypto state from primary to every replica (any sync_mode)."""
    from app.models import SyncStatus
    from app.services.node_sync.replicate import _primary_adapter, iter_replica_adapters

    primary_adapter = _primary_adapter(db, group)
    successes: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    client_name = (
        primary_config.client_name
        if primary_config.vpn_type != VpnType.openvpn
        else None
    )

    for replica_node, adapter in iter_replica_adapters(db, group):
        try:
            sync_vpn_crypto_from_primary(
                primary_adapter,
                adapter,
                primary_config.vpn_type,
                client_name=client_name,
            )
        except Exception as exc:
            logger.warning(
                "HA crypto sync failed on replica %s: %s",
                replica_node.name,
                exc,
            )
            errors.append(
                {
                    "node_id": replica_node.id,
                    "node_name": replica_node.name,
                    "error": _error_detail(exc),
                }
            )
            continue
        successes.append({"node_id": replica_node.id, "node_name": replica_node.name})

    if errors:
        group.sync_status = SyncStatus.failed
        group.last_sync_error = str(errors[0].get("error") or "crypto sync failed")
    elif successes:
        group.sync_status = SyncStatus.synced
        group.last_sync_error = None
    db.commit()

    return {"successes": successes, "errors": errors, "skipped": False}


def heal_crypto_drift(db, group) -> dict[str, object]:
    """Incremental reconcile heal: copy VPN crypto state from primary to all replicas."""
    from app.models import Node
    from app.services.node_manager import get_adapter_for_node
    from app.services.node_sync.groups import get_replica_nodes
    from app.services.node_sync.replicate import _primary_adapter

    primary_node = db.get(Node, group.primary_node_id)
    if primary_node is None:
        return {
            "success": False,
            "applied": [],
            "errors": [{"error": f"Primary node {group.primary_node_id} not found"}],
        }

    primary_adapter = _primary_adapter(db, group)
    applied: list[int] = []
    errors: list[dict[str, object]] = []

    for replica_node in get_replica_nodes(db, group):
        try:
            sync_all_vpn_crypto_from_primary(
                primary_adapter,
                get_adapter_for_node(replica_node),
            )
        except Exception as exc:
            errors.append(
                {
                    "node_id": replica_node.id,
                    "node_name": replica_node.name,
                    "error": _error_detail(exc),
                }
            )
            continue
        applied.append(replica_node.id)

    return {"success": not errors, "applied": applied, "errors": errors}

