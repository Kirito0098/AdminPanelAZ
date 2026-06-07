"""Node resource metrics persistence and history queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import NodeResourceSample

settings = get_settings()

VALID_PERIODS = frozenset({"1d", "7d", "30d"})
PERIOD_DELTAS = {
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
BUCKET_SECONDS = {
    "1d": 300,
    "7d": 1800,
    "30d": 7200,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _bytes_to_mb(value: int | float | None) -> int:
    if not value:
        return 0
    return int(value) // (1024 * 1024)


def metrics_to_sample_fields(metrics: dict[str, Any]) -> dict[str, Any]:
    load = metrics.get("load_average") or {}
    return {
        "cpu_percent": float(metrics.get("cpu_percent") or 0),
        "memory_percent": float(metrics.get("memory_percent") or 0),
        "memory_used_mb": _bytes_to_mb(metrics.get("memory_used")),
        "memory_total_mb": _bytes_to_mb(metrics.get("memory_total")),
        "disk_percent": float(metrics.get("disk_percent") or 0),
        "load_1": load.get("load_1m"),
        "load_5": load.get("load_5m"),
        "load_15": load.get("load_15m"),
    }


def persist_sample(db: Session, node_id: int, metrics: dict[str, Any]) -> NodeResourceSample:
    sample = NodeResourceSample(node_id=node_id, **metrics_to_sample_fields(metrics))
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


def purge_old_samples(db: Session) -> int:
    cutoff = _utcnow() - timedelta(days=settings.resource_metrics_retention_days)
    deleted = (
        db.query(NodeResourceSample)
        .filter(NodeResourceSample.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    if deleted:
        db.commit()
    return deleted


def _bucket_key(ts: datetime, bucket_seconds: int) -> int:
    epoch = int(ts.replace(tzinfo=timezone.utc).timestamp())
    return epoch - (epoch % bucket_seconds)


def _aggregate_bucket(samples: list[NodeResourceSample]) -> dict[str, Any]:
    count = len(samples)
    if count == 0:
        return {}
    avg = lambda attr: round(sum(getattr(s, attr) or 0 for s in samples) / count, 1)
    loads = [s.load_1 for s in samples if s.load_1 is not None]
    load_5 = [s.load_5 for s in samples if s.load_5 is not None]
    load_15 = [s.load_15 for s in samples if s.load_15 is not None]
    latest = max(samples, key=lambda s: s.created_at)
    return {
        "timestamp": latest.created_at,
        "cpu_percent": avg("cpu_percent"),
        "memory_percent": avg("memory_percent"),
        "memory_used_mb": int(sum(s.memory_used_mb for s in samples) / count),
        "memory_total_mb": latest.memory_total_mb,
        "disk_percent": avg("disk_percent"),
        "load_1": round(sum(loads) / len(loads), 2) if loads else None,
        "load_5": round(sum(load_5) / len(load_5), 2) if load_5 else None,
        "load_15": round(sum(load_15) / len(load_15), 2) if load_15 else None,
    }


def query_history(db: Session, node_id: int, period: str) -> tuple[list[dict[str, Any]], int]:
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period: {period}")

    since = _utcnow() - PERIOD_DELTAS[period]
    raw_samples = (
        db.query(NodeResourceSample)
        .filter(NodeResourceSample.node_id == node_id, NodeResourceSample.created_at >= since)
        .order_by(NodeResourceSample.created_at.asc())
        .all()
    )
    raw_count = len(raw_samples)
    if not raw_samples:
        return [], 0

    bucket_seconds = BUCKET_SECONDS[period]
    buckets: dict[int, list[NodeResourceSample]] = {}
    for sample in raw_samples:
        key = _bucket_key(sample.created_at, bucket_seconds)
        buckets.setdefault(key, []).append(sample)

    points = [_aggregate_bucket(buckets[key]) for key in sorted(buckets)]
    return points, raw_count
