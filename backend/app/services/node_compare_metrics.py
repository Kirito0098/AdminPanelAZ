"""Aggregate per-node compare metrics for multi-node dashboard."""

from __future__ import annotations

import time
from threading import Lock

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import UserTrafficStatProtocol
from app.services.node_adapter import NodeAdapter

# CIDR route totals change rarely; avoid get_routing_overview on every NOC tick.
_CIDR_ROUTES_TTL_SECONDS = 300
_cidr_routes_lock = Lock()
_cidr_routes_cache: dict[int, tuple[float, int | None]] = {}


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


def extract_cidr_routes_count(
    adapter: NodeAdapter,
    *,
    node_id: int | None = None,
    ttl_seconds: int | None = _CIDR_ROUTES_TTL_SECONDS,
) -> int | None:
    ttl = 0 if ttl_seconds is None else max(0, int(ttl_seconds))
    now = time.monotonic()
    if node_id is not None and ttl > 0:
        with _cidr_routes_lock:
            entry = _cidr_routes_cache.get(int(node_id))
            if entry is not None and now < entry[0]:
                return entry[1]

    value: int | None = None
    try:
        overview = adapter.get_routing_overview()
        route_stats = overview.get("route_stats") or {}
        if route_stats.get("result_route_ips_count") is not None:
            value = int(route_stats.get("result_route_ips_count") or 0)
        elif route_stats.get("config_include_total") is not None:
            value = int(route_stats.get("config_include_total") or 0)
    except Exception:
        value = None

    if node_id is not None and ttl > 0:
        with _cidr_routes_lock:
            _cidr_routes_cache[int(node_id)] = (now + ttl, value)
    return value


def clear_cidr_routes_count_cache() -> None:
    with _cidr_routes_lock:
        _cidr_routes_cache.clear()
