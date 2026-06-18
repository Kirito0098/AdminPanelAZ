"""Sustained resource alert checks against metrics history in DB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy.orm import Session

from app.models import NodeResourceSample, PanelResourceSample


class SustainedMetricSource(str, Enum):
    node_cpu = "node_cpu"
    node_ram = "node_ram"
    panel_host_cpu = "panel_host_cpu"
    panel_host_ram = "panel_host_ram"
    panel_backend_cpu = "panel_backend_cpu"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _min_samples(sustained_seconds: int, sample_interval_seconds: int) -> int:
    interval = max(1, sample_interval_seconds)
    window = max(0, sustained_seconds)
    return max(2, (window + interval - 1) // interval)


def _sample_value(sample: NodeResourceSample | PanelResourceSample, source: SustainedMetricSource) -> float:
    if source == SustainedMetricSource.node_cpu:
        return float(sample.cpu_percent)
    if source == SustainedMetricSource.node_ram:
        return float(sample.memory_percent)
    if source == SustainedMetricSource.panel_host_cpu:
        return float(sample.host_cpu_percent)
    if source == SustainedMetricSource.panel_host_ram:
        return float(sample.host_memory_percent)
    return float(sample.backend_cpu_percent)


def _load_samples(
    db: Session,
    *,
    source: SustainedMetricSource,
    node_id: int | None,
    cutoff: datetime,
) -> list[NodeResourceSample | PanelResourceSample]:
    if source in (SustainedMetricSource.node_cpu, SustainedMetricSource.node_ram):
        if node_id is None:
            return []
        return (
            db.query(NodeResourceSample)
            .filter(
                NodeResourceSample.node_id == node_id,
                NodeResourceSample.created_at >= cutoff,
            )
            .order_by(NodeResourceSample.created_at.asc())
            .all()
        )
    return (
        db.query(PanelResourceSample)
        .filter(PanelResourceSample.created_at >= cutoff)
        .order_by(PanelResourceSample.created_at.asc())
        .all()
    )


def is_sustained_high(
    db: Session,
    *,
    source: SustainedMetricSource,
    node_id: int | None,
    threshold: float,
    current_value: float,
    sustained_seconds: int,
    sample_interval_seconds: int,
) -> tuple[bool, str | None]:
    """Return True when metric stayed at/above threshold for the configured window."""
    if current_value < threshold:
        return False, None
    if sustained_seconds <= 0:
        return True, None

    cutoff = _utcnow() - timedelta(seconds=sustained_seconds)
    samples = _load_samples(db, source=source, node_id=node_id, cutoff=cutoff)
    values = [_sample_value(sample, source) for sample in samples]
    required = _min_samples(sustained_seconds, sample_interval_seconds)

    if len(values) < required:
        return False, None
    if any(value < threshold for value in values):
        return False, None

    avg = sum(values) / len(values)
    minutes = sustained_seconds / 60
    if minutes >= 1:
        window_label = f"{minutes:.0f} мин" if minutes == int(minutes) else f"{minutes:.1f} мин"
    else:
        window_label = f"{sustained_seconds} сек"
    return True, f"средн. {avg:.1f}% за {window_label} ({len(values)} замеров)"


def format_alert_details(
    current_value: float,
    threshold: float,
    sustained_detail: str | None,
) -> str:
    base = f"{current_value:.1f}% (порог {threshold:.0f}%)"
    if sustained_detail:
        return f"{base}, {sustained_detail}"
    return base
