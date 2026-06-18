"""Panel process metrics persistence and history queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PanelResourceSample
from app.services.panel_resource_collector import collect_panel_metrics

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


def metrics_to_sample_fields(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "backend_cpu_percent": float(metrics.get("backend_cpu_percent") or 0),
        "backend_memory_mb": int(metrics.get("backend_memory_mb") or 0),
        "backend_workers": int(metrics.get("backend_workers") or 0),
        "nginx_memory_mb": metrics.get("nginx_memory_mb"),
        "watchdog_memory_mb": metrics.get("watchdog_memory_mb"),
        "frontend_dev_memory_mb": metrics.get("frontend_dev_memory_mb"),
        "total_panel_memory_mb": int(metrics.get("total_panel_memory_mb") or 0),
        "host_cpu_percent": float(metrics.get("host_cpu_percent") or 0),
        "host_memory_percent": float(metrics.get("host_memory_percent") or 0),
        "host_memory_used_mb": int(metrics.get("host_memory_used_mb") or 0),
        "host_memory_total_mb": int(metrics.get("host_memory_total_mb") or 0),
        "host_disk_percent": float(metrics.get("host_disk_percent") or 0),
        "host_load_1": metrics.get("host_load_1"),
    }


def persist_sample(db: Session, metrics: dict[str, Any] | None = None) -> PanelResourceSample:
    payload = metrics if metrics is not None else collect_panel_metrics()
    sample = PanelResourceSample(**metrics_to_sample_fields(payload))
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


def persist_host_snapshot(
    db: Session,
    *,
    cpu_percent: float,
    memory_percent: float,
) -> PanelResourceSample:
    """Store host CPU/RAM snapshot for sustained resource alerts."""
    sample = PanelResourceSample(
        host_cpu_percent=float(cpu_percent),
        host_memory_percent=float(memory_percent),
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


def purge_old_samples(db: Session) -> int:
    cutoff = _utcnow() - timedelta(days=settings.panel_resource_metrics_retention_days)
    deleted = (
        db.query(PanelResourceSample)
        .filter(PanelResourceSample.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    if deleted:
        db.commit()
    return deleted


def _bucket_key(ts: datetime, bucket_seconds: int) -> int:
    epoch = int(ts.replace(tzinfo=timezone.utc).timestamp())
    return epoch - (epoch % bucket_seconds)


def _aggregate_bucket(samples: list[PanelResourceSample]) -> dict[str, Any]:
    count = len(samples)
    if count == 0:
        return {}

    def avg(attr: str) -> float:
        return round(sum(getattr(s, attr) or 0 for s in samples) / count, 1)
    nginx_vals = [s.nginx_memory_mb for s in samples if s.nginx_memory_mb is not None]
    watchdog_vals = [s.watchdog_memory_mb for s in samples if s.watchdog_memory_mb is not None]
    frontend_vals = [s.frontend_dev_memory_mb for s in samples if s.frontend_dev_memory_mb is not None]
    loads = [s.host_load_1 for s in samples if s.host_load_1 is not None]
    latest = max(samples, key=lambda s: s.created_at)
    return {
        "timestamp": latest.created_at,
        "backend_cpu_percent": avg("backend_cpu_percent"),
        "backend_memory_mb": int(sum(s.backend_memory_mb for s in samples) / count),
        "backend_workers": int(sum(s.backend_workers for s in samples) / count),
        "nginx_memory_mb": int(sum(nginx_vals) / len(nginx_vals)) if nginx_vals else None,
        "watchdog_memory_mb": int(sum(watchdog_vals) / len(watchdog_vals)) if watchdog_vals else None,
        "frontend_dev_memory_mb": int(sum(frontend_vals) / len(frontend_vals)) if frontend_vals else None,
        "total_panel_memory_mb": int(sum(s.total_panel_memory_mb for s in samples) / count),
        "host_cpu_percent": avg("host_cpu_percent"),
        "host_memory_percent": avg("host_memory_percent"),
        "host_memory_used_mb": int(sum(s.host_memory_used_mb for s in samples) / count),
        "host_memory_total_mb": latest.host_memory_total_mb,
        "host_disk_percent": avg("host_disk_percent"),
        "host_load_1": round(sum(loads) / len(loads), 2) if loads else None,
    }


def query_history(db: Session, period: str) -> tuple[list[dict[str, Any]], int]:
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period: {period}")

    since = _utcnow() - PERIOD_DELTAS[period]
    raw_samples = (
        db.query(PanelResourceSample)
        .filter(PanelResourceSample.created_at >= since)
        .order_by(PanelResourceSample.created_at.asc())
        .all()
    )
    raw_count = len(raw_samples)
    if not raw_samples:
        return [], 0

    bucket_seconds = BUCKET_SECONDS[period]
    buckets: dict[int, list[PanelResourceSample]] = {}
    for sample in raw_samples:
        key = _bucket_key(sample.created_at, bucket_seconds)
        buckets.setdefault(key, []).append(sample)

    points = [_aggregate_bucket(buckets[key]) for key in sorted(buckets)]
    return points, raw_count
