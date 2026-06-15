"""Prometheus metrics exposition for panel observability."""

from __future__ import annotations

from datetime import datetime

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Node, NodeStatus, UserTrafficSample

settings = get_settings()

_registry = CollectorRegistry()
_traffic_collector_lag = Gauge(
    "traffic_collector_lag_seconds",
    "Seconds since the newest traffic sample was stored",
    registry=_registry,
)
_nodes_online = Gauge(
    "node_health_online_total",
    "Number of nodes marked online in the panel database",
    registry=_registry,
)
_nodes_total = Gauge(
    "node_health_nodes_total",
    "Total number of registered nodes",
    registry=_registry,
)
_traffic_sync_enabled = Gauge(
    "traffic_sync_enabled",
    "Whether traffic sync worker is enabled (1=yes)",
    registry=_registry,
)


def refresh_metrics(db: Session) -> None:
    _traffic_sync_enabled.set(1 if settings.traffic_sync_enabled else 0)

    last_sample = db.query(func.max(UserTrafficSample.created_at)).scalar()
    if last_sample is None:
        _traffic_collector_lag.set(-1)
    else:
        lag = max(0, int((datetime.utcnow() - last_sample).total_seconds()))
        _traffic_collector_lag.set(lag)

    total_nodes = db.query(func.count(Node.id)).scalar() or 0
    online_nodes = (
        db.query(func.count(Node.id)).filter(Node.status == NodeStatus.online).scalar() or 0
    )
    _nodes_total.set(int(total_nodes))
    _nodes_online.set(int(online_nodes))


def render_metrics(db: Session) -> tuple[bytes, str]:
    refresh_metrics(db)
    return generate_latest(_registry), CONTENT_TYPE_LATEST
