"""Monitoring overview builders with endpoint formatting and geo enrichment."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.models import Node, NodeStatus, NodeSyncGroup, VpnConfig, VpnType
from app.schemas import (
    GlobalDashboardSummary,
    HaNodePresence,
    MonitoringNodeSummary,
    MonitoringOverview,
    MonitoringService,
    OpenVpnClient,
    VpnConfigHaInfo,
    WireGuardPeer,
)
from app.services.node_sync.groups import build_ha_metadata
from app.services.ip_geo import is_local_geoip_loaded, lookup_ips_geo, parse_client_endpoint
from app.services.node_health_score import compute_node_health_score
from app.services.node_manager import get_active_node, get_adapter_for_node
from app.services.node_compare_metrics import extract_cidr_routes_count, get_traffic_totals_by_node
from app.services.resource_metrics import get_latest_samples_by_node
from app.services.wireguard_status import wireguard_peer_is_online as _wg_is_online

HaMode = Literal["dedupe", "raw"]


def resolve_geoip_mode() -> Literal["local_mmdb", "ip_api", "none"]:
    if is_local_geoip_loaded():
        return "local_mmdb"
    return "ip_api"


def _node_status_value(node: Node) -> str:
    return node.status.value if hasattr(node.status, "value") else str(node.status)


def _collect_nodes_monitoring_data(db: Session) -> list[dict]:
    nodes = db.query(Node).order_by(Node.id.asc()).all()
    latest_metrics = get_latest_samples_by_node(db)
    traffic_totals = get_traffic_totals_by_node(db)
    node_payloads: list[dict] = []

    for node in nodes:
        sample = latest_metrics.get(node.id)
        payload = {
            "node": node,
            "ovpn_clients": [],
            "wireguard_peers": [],
            "services": [],
            "server_ip": None,
            "error": None,
            "cpu_percent": round(sample.cpu_percent, 1) if sample else None,
            "memory_percent": round(sample.memory_percent, 1) if sample else None,
            "total_traffic_bytes": traffic_totals.get(node.id),
            "cidr_routes_count": None,
        }
        try:
            adapter = get_adapter_for_node(node)
            ovpn_clients, _ = adapter.get_openvpn_status_snapshot()
            wireguard_peers = adapter.parse_wireguard_status()
            payload.update(
                {
                    "ovpn_clients": ovpn_clients,
                    "wireguard_peers": wireguard_peers,
                    "services": adapter.get_service_status(),
                    "server_ip": adapter.get_server_ip(),
                    "cidr_routes_count": extract_cidr_routes_count(adapter),
                }
            )
        except Exception as exc:
            payload["error"] = str(exc)
        node_payloads.append(payload)

    return node_payloads


def _build_node_summary(payload: dict) -> MonitoringNodeSummary:
    node: Node = payload["node"]
    ovpn_clients: list[OpenVpnClient] = payload["ovpn_clients"]
    wireguard_peers: list[WireGuardPeer] = payload["wireguard_peers"]
    services: list[MonitoringService] = payload["services"]
    status = _node_status_value(node)
    active_services = sum(1 for service in services if service.active)
    total_services = len(services)
    health_score, health_level = compute_node_health_score(
        status=status,
        error=payload.get("error"),
        cpu_percent=payload.get("cpu_percent"),
        memory_percent=payload.get("memory_percent"),
        active_services=active_services,
        total_services=total_services,
    )
    return MonitoringNodeSummary(
        node_id=node.id,
        node_name=node.name,
        status=status,
        connected_openvpn=len(ovpn_clients),
        connected_wireguard=sum(1 for peer in wireguard_peers if _wg_is_online(peer)),
        active_services=active_services,
        total_services=total_services,
        cpu_percent=payload.get("cpu_percent"),
        memory_percent=payload.get("memory_percent"),
        total_traffic_bytes=payload.get("total_traffic_bytes"),
        cidr_routes_count=payload.get("cidr_routes_count"),
        error=payload["error"],
        health_score=health_score,
        health_level=health_level,
    )


def build_global_dashboard_summary(db: Session) -> GlobalDashboardSummary:
    node_payloads = _collect_nodes_monitoring_data(db)
    nodes_summary: list[MonitoringNodeSummary] = []
    nodes_online = 0
    total_connected_openvpn = 0
    total_connected_wireguard = 0

    for payload in node_payloads:
        node: Node = payload["node"]
        summary = _build_node_summary(payload)
        if node.status == NodeStatus.online:
            nodes_online += 1
        total_connected_openvpn += summary.connected_openvpn
        total_connected_wireguard += summary.connected_wireguard
        nodes_summary.append(summary)

    return GlobalDashboardSummary(
        timestamp=datetime.utcnow(),
        nodes_summary=nodes_summary,
        nodes_online=nodes_online,
        nodes_total=len(node_payloads),
        total_connected_openvpn=total_connected_openvpn,
        total_connected_wireguard=total_connected_wireguard,
    )


def _collect_lookup_ips(
    openvpn_clients: list[OpenVpnClient],
    wireguard_peers: list[WireGuardPeer],
) -> list[str | None]:
    ips: list[str | None] = []
    for client in openvpn_clients:
        parsed = parse_client_endpoint(client.real_address)
        ips.append(parsed.get("lookup_ip"))
    for peer in wireguard_peers:
        parsed = parse_client_endpoint(peer.endpoint)
        ips.append(parsed.get("lookup_ip"))
    return ips


def _apply_geo_fields(
    *,
    endpoint: str | None,
    geo_map: dict[str, dict[str, str | None]],
    extra: dict | None = None,
) -> dict:
    parsed = parse_client_endpoint(endpoint)
    lookup_ip = (parsed.get("lookup_ip") or "").strip("[]")
    geo = geo_map.get(lookup_ip, {}) if lookup_ip else {}
    payload = {
        "display_address": parsed.get("display_address"),
        "client_ip": parsed.get("client_ip"),
        "city": geo.get("city"),
        "country": geo.get("country"),
        "isp": geo.get("isp"),
        "location_label": geo.get("location_label"),
        "geo_label": geo.get("geo_label"),
    }
    if extra:
        payload.update(extra)
    return payload


def enrich_openvpn_clients(
    clients: list[OpenVpnClient],
    geo_map: dict[str, dict[str, str | None]],
    *,
    node_id: int | None = None,
    node_name: str | None = None,
) -> list[OpenVpnClient]:
    extra = {"node_id": node_id, "node_name": node_name} if node_id is not None else None
    return [
        client.model_copy(
            update=_apply_geo_fields(endpoint=client.real_address, geo_map=geo_map, extra=extra),
        )
        for client in clients
    ]


def enrich_wireguard_peers(
    peers: list[WireGuardPeer],
    geo_map: dict[str, dict[str, str | None]],
    *,
    node_id: int | None = None,
    node_name: str | None = None,
) -> list[WireGuardPeer]:
    extra = {"node_id": node_id, "node_name": node_name} if node_id is not None else None
    return [
        peer.model_copy(
            update=_apply_geo_fields(endpoint=peer.endpoint, geo_map=geo_map, extra=extra),
        )
        for peer in peers
    ]


def build_monitoring_overview_for_node(db: Session, node: Node) -> MonitoringOverview:
    adapter = get_adapter_for_node(node)
    ovpn_clients, openvpn_data_source = adapter.get_openvpn_status_snapshot()
    wireguard_peers = adapter.parse_wireguard_status()
    services = adapter.get_service_status()
    geo_map = lookup_ips_geo(_collect_lookup_ips(ovpn_clients, wireguard_peers))
    return MonitoringOverview(
        scope="node",
        services=services,
        openvpn_clients=enrich_openvpn_clients(ovpn_clients, geo_map),
        wireguard_peers=enrich_wireguard_peers(wireguard_peers, geo_map),
        server_ip=adapter.get_server_ip(),
        timestamp=datetime.utcnow(),
        node_id=node.id,
        node_name=node.name,
        openvpn_data_source=openvpn_data_source,
        nodes_summary=[],
        nodes_online=1 if node.status == NodeStatus.online else 0,
        nodes_total=1,
        total_connected_openvpn=len(ovpn_clients),
        total_connected_wireguard=sum(1 for peer in wireguard_peers if _wg_is_online(peer)),
        served_from_cache=False,
        geoip_mode=resolve_geoip_mode(),
        ha_mode="dedupe",
    )


def build_monitoring_overview(db: Session) -> MonitoringOverview:
    node = get_active_node(db)
    return build_monitoring_overview_for_node(db, node)


_HaLookupKey = tuple[int, str, str]
_AggregationKey = tuple[str, ...]


def _build_ha_monitoring_lookup(db: Session) -> dict[_HaLookupKey, tuple[_AggregationKey, VpnConfigHaInfo]]:
    configs = (
        db.query(VpnConfig)
        .filter(
            (VpnConfig.sync_group_id.isnot(None)) | (VpnConfig.ha_primary_config_id.isnot(None)),
        )
        .all()
    )
    if not configs:
        return {}

    primary_ids = {config.ha_primary_config_id for config in configs if config.ha_primary_config_id}
    primaries = {
        config.id: config
        for config in db.query(VpnConfig).filter(VpnConfig.id.in_(primary_ids)).all()
    } if primary_ids else {}

    group_ids = {config.sync_group_id for config in configs if config.sync_group_id}
    for config in configs:
        if config.ha_primary_config_id:
            primary = primaries.get(config.ha_primary_config_id)
            if primary and primary.sync_group_id:
                group_ids.add(primary.sync_group_id)
    groups = {
        group.id: group
        for group in db.query(NodeSyncGroup).filter(NodeSyncGroup.id.in_(group_ids)).all()
    } if group_ids else {}

    lookup: dict[_HaLookupKey, tuple[_AggregationKey, VpnConfigHaInfo]] = {}
    for config in configs:
        sync_group_id = config.sync_group_id
        if config.ha_primary_config_id:
            primary = primaries.get(config.ha_primary_config_id)
            sync_group_id = primary.sync_group_id if primary else sync_group_id
        if not sync_group_id:
            continue
        group = groups.get(sync_group_id)
        meta = build_ha_metadata(group)
        if not meta:
            continue
        protocol = config.vpn_type.value
        client_lower = config.client_name.lower()
        agg_key = ("ha", sync_group_id, protocol, client_lower)
        lookup[(config.node_id, client_lower, protocol)] = (agg_key, VpnConfigHaInfo(**meta))
    return lookup


def _aggregation_key_for_client(
    *,
    node_id: int | None,
    client_name: str,
    protocol: str,
    ha_lookup: dict[_HaLookupKey, tuple[_AggregationKey, VpnConfigHaInfo]],
) -> tuple[_AggregationKey, VpnConfigHaInfo | None]:
    client_lower = client_name.lower()
    if node_id is not None:
        entry = ha_lookup.get((node_id, client_lower, protocol))
        if entry:
            return entry
    return (("solo", node_id or 0, protocol, client_lower), None)


def _ha_nodes_from_group(group_clients: list[OpenVpnClient] | list[WireGuardPeer]) -> list[HaNodePresence]:
    seen: dict[int, HaNodePresence] = {}
    for item in group_clients:
        node_id = getattr(item, "node_id", None)
        if node_id is None:
            continue
        node_name = getattr(item, "node_name", None) or f"node-{node_id}"
        seen[node_id] = HaNodePresence(node_id=node_id, node_name=node_name, online=True)
    return list(seen.values())


def _aggregate_ha_openvpn_clients(
    clients: list[OpenVpnClient],
    ha_lookup: dict[_HaLookupKey, tuple[_AggregationKey, VpnConfigHaInfo]],
) -> list[OpenVpnClient]:
    grouped: dict[_AggregationKey, list[OpenVpnClient]] = {}
    ha_by_key: dict[_AggregationKey, VpnConfigHaInfo] = {}
    for client in clients:
        agg_key, ha = _aggregation_key_for_client(
            node_id=client.node_id,
            client_name=client.common_name,
            protocol=VpnType.openvpn.value,
            ha_lookup=ha_lookup,
        )
        grouped.setdefault(agg_key, []).append(client)
        if ha:
            ha_by_key[agg_key] = ha

    aggregated: list[OpenVpnClient] = []
    for agg_key, group_clients in grouped.items():
        chosen = max(group_clients, key=lambda item: (item.bytes_received + item.bytes_sent, item.connected_since_ts))
        ha = ha_by_key.get(agg_key)
        updates: dict = {"ha": ha}
        if ha:
            updates["active_node_id"] = chosen.node_id
            updates["active_node_name"] = chosen.node_name
            updates["ha_nodes"] = _ha_nodes_from_group(group_clients)
            updates["node_id"] = chosen.node_id
            updates["node_name"] = chosen.node_name
        aggregated.append(chosen.model_copy(update=updates))
    return aggregated


def _aggregate_ha_wireguard_peers(
    peers: list[WireGuardPeer],
    ha_lookup: dict[_HaLookupKey, tuple[_AggregationKey, VpnConfigHaInfo]],
) -> list[WireGuardPeer]:
    grouped: dict[_AggregationKey, list[WireGuardPeer]] = {}
    ha_by_key: dict[_AggregationKey, VpnConfigHaInfo] = {}
    for peer in peers:
        client_name = (peer.client_name or "").strip() or peer.public_key
        agg_key, ha = _aggregation_key_for_client(
            node_id=peer.node_id,
            client_name=client_name,
            protocol=VpnType.wireguard.value,
            ha_lookup=ha_lookup,
        )
        grouped.setdefault(agg_key, []).append(peer)
        if ha:
            ha_by_key[agg_key] = ha

    aggregated: list[WireGuardPeer] = []
    for agg_key, group_peers in grouped.items():
        chosen = max(
            group_peers,
            key=lambda item: (
                1 if _wg_is_online(item) else 0,
                item.transfer_rx + item.transfer_tx,
            ),
        )
        ha = ha_by_key.get(agg_key)
        updates: dict = {"ha": ha}
        if ha:
            updates["active_node_id"] = chosen.node_id
            updates["active_node_name"] = chosen.node_name
            updates["ha_nodes"] = _ha_nodes_from_group(group_peers)
            updates["node_id"] = chosen.node_id
            updates["node_name"] = chosen.node_name
        aggregated.append(chosen.model_copy(update=updates))
    return aggregated


def _annotate_raw_ha_clients(
    clients: list[OpenVpnClient],
    ha_lookup: dict[_HaLookupKey, tuple[_AggregationKey, VpnConfigHaInfo]],
) -> list[OpenVpnClient]:
    annotated: list[OpenVpnClient] = []
    for client in clients:
        _agg_key, ha = _aggregation_key_for_client(
            node_id=client.node_id,
            client_name=client.common_name,
            protocol=VpnType.openvpn.value,
            ha_lookup=ha_lookup,
        )
        updates: dict = {
            "ha": ha,
            "active_node_id": client.node_id,
            "active_node_name": client.node_name,
        }
        if ha and client.node_id is not None:
            updates["ha_nodes"] = [
                HaNodePresence(
                    node_id=client.node_id,
                    node_name=client.node_name or f"node-{client.node_id}",
                    online=True,
                )
            ]
        annotated.append(client.model_copy(update=updates))
    return annotated


def _annotate_raw_ha_peers(
    peers: list[WireGuardPeer],
    ha_lookup: dict[_HaLookupKey, tuple[_AggregationKey, VpnConfigHaInfo]],
) -> list[WireGuardPeer]:
    annotated: list[WireGuardPeer] = []
    for peer in peers:
        client_name = (peer.client_name or "").strip() or peer.public_key
        _agg_key, ha = _aggregation_key_for_client(
            node_id=peer.node_id,
            client_name=client_name,
            protocol=VpnType.wireguard.value,
            ha_lookup=ha_lookup,
        )
        updates: dict = {
            "ha": ha,
            "active_node_id": peer.node_id,
            "active_node_name": peer.node_name,
        }
        if ha and peer.node_id is not None:
            updates["ha_nodes"] = [
                HaNodePresence(
                    node_id=peer.node_id,
                    node_name=peer.node_name or f"node-{peer.node_id}",
                    online=True,
                )
            ]
        annotated.append(peer.model_copy(update=updates))
    return annotated


def build_federated_monitoring_overview(
    db: Session,
    *,
    ha_mode: HaMode = "dedupe",
) -> MonitoringOverview:
    node_payloads = _collect_nodes_monitoring_data(db)
    lookup_ips: list[str | None] = []
    for payload in node_payloads:
        lookup_ips.extend(
            _collect_lookup_ips(payload["ovpn_clients"], payload["wireguard_peers"]),
        )

    geo_map = lookup_ips_geo(lookup_ips)
    all_openvpn: list[OpenVpnClient] = []
    all_wireguard: list[WireGuardPeer] = []
    nodes_summary: list[MonitoringNodeSummary] = []
    nodes_online = 0
    total_connected_openvpn = 0
    total_connected_wireguard = 0
    server_ips: list[str] = []

    for payload in node_payloads:
        node: Node = payload["node"]
        ovpn_clients: list[OpenVpnClient] = payload["ovpn_clients"]
        wireguard_peers: list[WireGuardPeer] = payload["wireguard_peers"]
        summary = _build_node_summary(payload)
        if node.status == NodeStatus.online:
            nodes_online += 1
        total_connected_openvpn += summary.connected_openvpn
        total_connected_wireguard += summary.connected_wireguard
        if payload["server_ip"]:
            server_ips.append(payload["server_ip"])
        all_openvpn.extend(enrich_openvpn_clients(ovpn_clients, geo_map, node_id=node.id, node_name=node.name))
        all_wireguard.extend(enrich_wireguard_peers(wireguard_peers, geo_map, node_id=node.id, node_name=node.name))
        nodes_summary.append(summary)

    ha_lookup = _build_ha_monitoring_lookup(db)
    if ha_mode == "raw":
        all_openvpn = _annotate_raw_ha_clients(all_openvpn, ha_lookup)
        all_wireguard = _annotate_raw_ha_peers(all_wireguard, ha_lookup)
        total_connected_openvpn = len(all_openvpn)
        total_connected_wireguard = sum(1 for peer in all_wireguard if _wg_is_online(peer))
    else:
        all_openvpn = _aggregate_ha_openvpn_clients(all_openvpn, ha_lookup)
        all_wireguard = _aggregate_ha_wireguard_peers(all_wireguard, ha_lookup)
        total_connected_openvpn = len(all_openvpn)
        total_connected_wireguard = sum(1 for peer in all_wireguard if _wg_is_online(peer))

    nodes = [payload["node"] for payload in node_payloads]
    active_node = None
    try:
        active_node = get_active_node(db)
    except Exception:
        active_node = nodes[0] if nodes else None

    return MonitoringOverview(
        scope="all",
        services=[],
        openvpn_clients=all_openvpn,
        wireguard_peers=all_wireguard,
        server_ip=", ".join(sorted(set(server_ips))) if server_ips else None,
        timestamp=datetime.utcnow(),
        node_id=active_node.id if active_node else None,
        node_name=active_node.name if active_node else None,
        openvpn_data_source="federated",
        nodes_summary=nodes_summary,
        nodes_online=nodes_online,
        nodes_total=len(nodes),
        total_connected_openvpn=total_connected_openvpn,
        total_connected_wireguard=total_connected_wireguard,
        served_from_cache=False,
        geoip_mode=resolve_geoip_mode(),
        ha_mode=ha_mode,
    )
