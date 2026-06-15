"""Geo-based node recommendation hint when issuing VPN configs."""

from __future__ import annotations

import ipaddress

from sqlalchemy.orm import Session

from app.models import Node, NodeStatus
from app.schemas import GeoRoutingHintResponse, GeoRoutingNodeHint
from app.services.ip_geo import lookup_ip_geo, lookup_ips_geo
from app.services.node_manager import get_adapter_for_node


def _normalize_client_ip(raw: str | None) -> str | None:
    if not raw:
        return None
    candidate = raw.split(",")[0].strip()
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _server_lookup_ip(server_ip: str | None) -> str | None:
    if not server_ip:
        return None
    first = server_ip.split(",")[0].strip()
    return first or None


def build_geo_routing_hint(db: Session, *, client_ip: str | None = None) -> GeoRoutingHintResponse:
    normalized_ip = _normalize_client_ip(client_ip)
    client_geo = lookup_ip_geo(normalized_ip) if normalized_ip else {}
    client_country = client_geo.get("country")

    nodes = db.query(Node).order_by(Node.id.asc()).all()
    server_ips: list[str | None] = []
    node_payloads: list[dict] = []

    for node in nodes:
        server_ip = None
        if node.status == NodeStatus.online:
            try:
                adapter = get_adapter_for_node(node)
                server_ip = adapter.get_server_ip()
            except Exception:
                server_ip = None
        lookup_ip = _server_lookup_ip(server_ip)
        server_ips.append(lookup_ip)
        node_payloads.append({"node": node, "server_ip": server_ip, "lookup_ip": lookup_ip})

    geo_by_ip = lookup_ips_geo(server_ips)
    hints: list[GeoRoutingNodeHint] = []
    best_node: Node | None = None
    best_score = -1

    for payload in node_payloads:
        node: Node = payload["node"]
        lookup_ip = payload["lookup_ip"]
        node_geo = geo_by_ip.get(lookup_ip or "", {}) if lookup_ip else {}
        country = node_geo.get("country")
        score = 0
        if node.status == NodeStatus.online:
            score = 1
            if client_country and country and client_country == country:
                score = 100
        if score > best_score:
            best_score = score
            best_node = node
        elif score == best_score and best_node is not None and node.name < best_node.name:
            best_node = node

    for payload in node_payloads:
        node: Node = payload["node"]
        lookup_ip = payload["lookup_ip"]
        node_geo = geo_by_ip.get(lookup_ip or "", {}) if lookup_ip else {}
        hints.append(
            GeoRoutingNodeHint(
                node_id=node.id,
                node_name=node.name,
                status=node.status.value if hasattr(node.status, "value") else str(node.status),
                server_ip=payload["server_ip"],
                country=node_geo.get("country"),
                city=node_geo.get("city"),
                geo_label=node_geo.get("geo_label"),
                is_recommended=best_node is not None and node.id == best_node.id,
            )
        )

    hint_message = None
    recommended_node_id = best_node.id if best_node else None
    recommended_node_name = best_node.name if best_node else None

    if not normalized_ip:
        hint_message = "Не удалось определить публичный IP клиента — подсказка по геолокации недоступна."
    elif not client_country:
        hint_message = "Геолокация клиента не определена."
    elif best_node and best_score >= 100:
        hint_message = f"Ближе узел «{best_node.name}» — тот же регион ({client_country})."
    elif best_node:
        hint_message = f"Рекомендуемый узел: «{best_node.name}» (online)."

    return GeoRoutingHintResponse(
        client_ip=normalized_ip,
        client_country=client_country,
        client_city=client_geo.get("city"),
        client_geo_label=client_geo.get("geo_label"),
        recommended_node_id=recommended_node_id,
        recommended_node_name=recommended_node_name,
        hint_message=hint_message,
        nodes=hints,
    )
