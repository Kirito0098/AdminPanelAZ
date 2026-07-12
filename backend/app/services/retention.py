"""Batch retention purge for traffic samples, action logs, and resource metrics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ConnectionCountSample, NodeResourceSample, PanelResourceSample, UserActionLog, UserTrafficSample


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _purge_model_before(
    db: Session,
    model,
    cutoff: datetime,
    *,
    batch_size: int,
) -> int:
    total = 0
    while True:
        ids = [
            row[0]
            for row in db.query(model.id)
            .filter(model.created_at < cutoff)
            .order_by(model.id.asc())
            .limit(batch_size)
            .all()
        ]
        if not ids:
            break
        deleted = db.query(model).filter(model.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        total += int(deleted or 0)
    return total


def run_retention_purge(db: Session) -> dict[str, int]:
    """Delete rows older than configured retention windows. Returns per-table counts."""
    settings = get_settings()
    batch_size = max(100, int(settings.retention_batch_size or 5000))
    now = _utcnow()
    counts: dict[str, int] = {}

    traffic_days = max(1, int(settings.traffic_sample_retention_days or 90))
    counts["user_traffic_sample"] = _purge_model_before(
        db,
        UserTrafficSample,
        now - timedelta(days=traffic_days),
        batch_size=batch_size,
    )

    log_days = max(1, int(settings.action_log_retention_days or 365))
    counts["user_action_log"] = _purge_model_before(
        db,
        UserActionLog,
        now - timedelta(days=log_days),
        batch_size=batch_size,
    )

    node_days = max(1, int(settings.resource_metrics_retention_days or 30))
    counts["node_resource_sample"] = _purge_model_before(
        db,
        NodeResourceSample,
        now - timedelta(days=node_days),
        batch_size=batch_size,
    )

    counts["connection_count_samples"] = _purge_model_before(
        db,
        ConnectionCountSample,
        now - timedelta(days=node_days),
        batch_size=batch_size,
    )

    panel_days = max(1, int(settings.panel_resource_metrics_retention_days or 30))
    counts["panel_resource_sample"] = _purge_model_before(
        db,
        PanelResourceSample,
        now - timedelta(days=panel_days),
        batch_size=batch_size,
    )

    counts["total"] = sum(counts.values())
    return counts
