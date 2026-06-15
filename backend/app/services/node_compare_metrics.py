"""Aggregate per-node compare metrics for multi-node dashboard."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import UserTrafficStatProtocol
from app.services.node_adapter import NodeAdapter


def get_traffic_totals_by_node(db: Session) -> dict[int, int]:
    rows = (
        db.query(
            UserTrafficStatProtocol.node_id,
            func.coalesce(
                func.sum(UserTrafficStatProtocol.total_received + UserTrafficStatProtocol.total_sent),
                0,
            ),
        )
        .group_by(UserTrafficStatProtocol.node_id)
        .all()
    )
    return {int(node_id): int(total or 0) for node_id, total in rows}


def extract_cidr_routes_count(adapter: NodeAdapter) -> int | None:
    try:
        overview = adapter.get_routing_overview()
        route_stats = overview.get("route_stats") or {}
        if route_stats.get("result_route_ips_count") is not None:
            return int(route_stats.get("result_route_ips_count") or 0)
        if route_stats.get("config_include_total") is not None:
            return int(route_stats.get("config_include_total") or 0)
    except Exception:
        return None
    return None
