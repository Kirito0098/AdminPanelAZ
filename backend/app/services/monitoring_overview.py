"""Monitoring overview builders with endpoint formatting and geo enrichment."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Node, NodeStatus
from app.schemas import (
    GlobalDashboardSummary,
    MonitoringNodeSummary,
    MonitoringOverview,
    MonitoringService,
    OpenVpnClient,
    WireGuardPeer,
)
from app.services.ip_geo import lookup_ips_geo, parse_client_endpoint
from app.services.node_manager import get_active_node, get_adapter_for_node
from app.services.node_compare_metrics import extract_cidr_routes_count, get_traffic_totals_by_node
from app.services.resource_metrics import get_latest_samples_by_node


def _wg_is_online(peer: WireGuardPeer) -> bool:
    return bool(peer.latest_handshake)


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
    return MonitoringNodeSummary(
        node_id=node.id,
        node_name=node.name,
        status=_node_status_value(node),
        connected_openvpn=len(ovpn_clients),
        connected_wireguard=sum(1 for peer in wireguard_peers if _wg_is_online(peer)),
        active_services=sum(1 for service in services if service.active),
        total_services=len(services),
        cpu_percent=payload.get("cpu_percent"),
        memory_percent=payload.get("memory_percent"),
        total_traffic_bytes=payload.get("total_traffic_bytes"),
        cidr_routes_count=payload.get("cidr_routes_count"),
        error=payload["error"],
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
    )


def build_monitoring_overview(db: Session) -> MonitoringOverview:
    node = get_active_node(db)
    return build_monitoring_overview_for_node(db, node)


def build_federated_monitoring_overview(db: Session) -> MonitoringOverview:
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
    )
