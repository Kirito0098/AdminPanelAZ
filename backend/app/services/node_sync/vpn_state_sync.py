"""HA auto-sync: copy VPN crypto state (WireGuard conf + OpenVPN easyrsa3) from primary to replica."""

from __future__ import annotations

from fastapi import HTTPException

from app.models import VpnType
from app.services.node_sync.openvpn_restart import restart_all_openvpn_servers

WIREGUARD_INTERFACES = ("antizapret", "vpn")


def sync_wireguard_state_from_primary(primary_adapter, replica_adapter) -> None:
    """Copy WireGuard server configs from primary and apply on replica."""
    for interface in WIREGUARD_INTERFACES:
        content = primary_adapter.read_wireguard_server_config(interface)
        replica_adapter.write_wireguard_server_config(interface, content)

    runtime = replica_adapter.apply_wireguard_runtime()
    if not runtime.get("success"):
        errors = runtime.get("errors") or []
        detail = "; ".join(
            str(entry.get("stderr") or entry.get("error") or entry)
            for entry in errors
        ) or "WireGuard runtime apply failed"
        raise HTTPException(status_code=500, detail=detail)

    replica_adapter.recreate_profiles()


def sync_openvpn_pki_from_primary(primary_adapter, replica_adapter) -> None:
    """Copy OpenVPN PKI (easyrsa3) from primary and reload services on replica."""
    archive = primary_adapter.export_easyrsa3_archive()
    replica_adapter.import_easyrsa3_archive(archive)
    replica_adapter.recreate_profiles()
    restart_result = restart_all_openvpn_servers(replica_adapter)
    if not restart_result.get("success"):
        failed = restart_result.get("failed") or []
        detail = "; ".join(
            str(entry.get("error") or entry.get("unit") or entry)
            for entry in failed
        ) or "OpenVPN restart failed after PKI sync"
        raise HTTPException(status_code=500, detail=detail)


def sync_vpn_crypto_from_primary(primary_adapter, replica_adapter, vpn_type: VpnType) -> None:
    """Copy primary VPN crypto material to replica for HA failover parity."""
    if vpn_type == VpnType.openvpn:
        sync_openvpn_pki_from_primary(primary_adapter, replica_adapter)
        return
    sync_wireguard_state_from_primary(primary_adapter, replica_adapter)


def sync_all_vpn_crypto_from_primary(primary_adapter, replica_adapter) -> None:
    """Copy both WireGuard and OpenVPN crypto state from primary to replica."""
    sync_wireguard_state_from_primary(primary_adapter, replica_adapter)
    sync_openvpn_pki_from_primary(primary_adapter, replica_adapter)


def heal_crypto_drift(db, group) -> dict[str, object]:
    """Incremental reconcile heal: copy VPN crypto state from primary to all replicas."""
    from app.models import Node
    from app.services.node_manager import get_adapter_for_node
    from app.services.node_sync.groups import get_replica_nodes

    primary_node = db.get(Node, group.primary_node_id)
    if primary_node is None:
        return {
            "success": False,
            "applied": [],
            "errors": [{"error": f"Primary node {group.primary_node_id} not found"}],
        }

    primary_adapter = get_adapter_for_node(primary_node)
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
                    "error": str(exc),
                }
            )
            continue
        applied.append(replica_node.id)

    return {"success": not errors, "applied": applied, "errors": errors}
