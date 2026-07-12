"""Connection count samples for NOC history charts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ConnectionCountSample, Node, NodeStatus
from app.services.node_manager import get_active_node, get_adapter_for_node
from app.services.wireguard_status import wireguard_peer_is_online

settings = get_settings()

VALID_PERIODS = frozenset({"1h", "6h", "24h"})
PERIOD_DELTAS = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
}
BUCKET_SECONDS = {
    "1h": 60,
    "6h": 300,
    "24h": 900,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def persist_connection_sample(
    db: Session,
    node_id: int,
    *,
    openvpn_count: int,
    wireguard_count: int,
) -> ConnectionCountSample:
    sample = ConnectionCountSample(
        node_id=node_id,
        openvpn_count=max(0, int(openvpn_count)),
        wireguard_count=max(0, int(wireguard_count)),
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


def collect_connection_samples(db: Session) -> int:
    """Collect per-node connection counts via adapters. Returns samples written."""
    nodes = db.query(Node).order_by(Node.id.asc()).all()
    written = 0
    for node in nodes:
        status = node.status.value if hasattr(node.status, "value") else str(node.status)
        if status != NodeStatus.online.value and status != "online":
            persist_connection_sample(db, node.id, openvpn_count=0, wireguard_count=0)
            written += 1
            continue
        try:
            adapter = get_adapter_for_node(node)
            ovpn_clients, _ = adapter.get_openvpn_status_snapshot()
            wg_peers = adapter.parse_wireguard_status()
            wg_online = sum(1 for peer in wg_peers if wireguard_peer_is_online(peer))
            persist_connection_sample(
                db,
                node.id,
                openvpn_count=len(ovpn_clients),
                wireguard_count=wg_online,
            )
            written += 1
        except Exception:
            persist_connection_sample(db, node.id, openvpn_count=0, wireguard_count=0)
            written += 1
    return written


def purge_old_connection_samples(db: Session) -> int:
    cutoff = _utcnow() - timedelta(days=settings.resource_metrics_retention_days)
    deleted = (
        db.query(ConnectionCountSample)
        .filter(ConnectionCountSample.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    if deleted:
        db.commit()
    return deleted


def _bucket_key(ts: datetime, bucket_seconds: int) -> int:
    epoch = int(ts.replace(tzinfo=timezone.utc).timestamp())
    return epoch - (epoch % bucket_seconds)


def _aggregate_bucket(samples: list[ConnectionCountSample], *, sum_nodes: bool) -> dict[str, Any]:
    if not samples:
        return {}
    latest = max(samples, key=lambda s: s.created_at)
    if sum_nodes:
        # One sample per node near the bucket — sum last per node_id
        by_node: dict[int, ConnectionCountSample] = {}
        for sample in samples:
            prev = by_node.get(sample.node_id)
            if prev is None or sample.created_at >= prev.created_at:
                by_node[sample.node_id] = sample
        ovpn = sum(s.openvpn_count for s in by_node.values())
        wg = sum(s.wireguard_count for s in by_node.values())
    else:
        ovpn = int(sum(s.openvpn_count for s in samples) / len(samples))
        wg = int(sum(s.wireguard_count for s in samples) / len(samples))
    return {
        "timestamp": latest.created_at,
        "openvpn": ovpn,
        "wireguard": wg,
        "total": ovpn + wg,
    }


def query_connection_history(
    db: Session,
    *,
    period: str,
    scope: str = "node",
) -> tuple[list[dict[str, Any]], int]:
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period: {period}")
    if scope not in {"node", "all"}:
        raise ValueError(f"Invalid scope: {scope}")

    since = _utcnow() - PERIOD_DELTAS[period]
    query = db.query(ConnectionCountSample).filter(ConnectionCountSample.created_at >= since)
    if scope == "node":
        node = get_active_node(db)
        query = query.filter(ConnectionCountSample.node_id == node.id)

    raw_samples = query.order_by(ConnectionCountSample.created_at.asc()).all()
    raw_count = len(raw_samples)
    if not raw_samples:
        return [], 0

    bucket_seconds = BUCKET_SECONDS[period]
    buckets: dict[int, list[ConnectionCountSample]] = {}
    for sample in raw_samples:
        key = _bucket_key(sample.created_at, bucket_seconds)
        buckets.setdefault(key, []).append(sample)

    points = [
        _aggregate_bucket(buckets[key], sum_nodes=(scope == "all"))
        for key in sorted(buckets)
    ]
    return points, raw_count
