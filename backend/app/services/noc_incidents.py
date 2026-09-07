"""Build mixed NOC incident feed for the monitoring page."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import AlertRule, AlertRuleMetric, CidrDbRefreshLog, Node, NodeStatus
from app.schemas import NocIncidentItem, NocIncidentsResponse
from app.services.alert_rules import format_rule_condition
from app.services.monitoring_overview import _build_node_summary, _collect_nodes_monitoring_data
from app.services.node_manager import _is_vpn_node, get_active_node

_CIDR_OK_STATUSES = frozenset({"ok", "success"})
_ALERT_WINDOW_DAYS = 7
_CIDR_WINDOW_HOURS = 48


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _alert_severity(metric: AlertRuleMetric | str) -> str:
    key = metric.value if hasattr(metric, "value") else str(metric)
    if key in {
        AlertRuleMetric.nodes_offline.value,
        AlertRuleMetric.node_offline_seconds.value,
    }:
        return "danger"
    return "warning"


def build_noc_incidents(db: Session, *, limit: int = 20) -> NocIncidentsResponse:
    limit = max(1, min(100, int(limit)))
    now = _utcnow()
    items: list[NocIncidentItem] = []

    alert_since = now - timedelta(days=_ALERT_WINDOW_DAYS)
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.last_triggered_at.isnot(None))
        .order_by(AlertRule.last_triggered_at.desc())
        .all()
    )
    for rule in rules:
        triggered = _as_naive_utc(rule.last_triggered_at)
        if triggered is None or triggered < alert_since:
            continue
        items.append(
            NocIncidentItem(
                id=f"alert:{rule.id}",
                kind="alert_rule",
                severity=_alert_severity(rule.metric),  # type: ignore[arg-type]
                title=rule.name,
                detail=format_rule_condition(rule),
                at=triggered,
                href="/settings?tab=monitoring",
            )
        )

    nodes = db.query(Node).order_by(Node.id.asc()).all()
    payloads: list[dict] = []
    summary_by_id: dict[int, object] = {}
    try:
        # One collect for node health + active-node services (was global summary + overview).
        payloads = _collect_nodes_monitoring_data(db)
        summary_by_id = {payload["node"].id: _build_node_summary(payload) for payload in payloads}
    except Exception:
        payloads = []
        summary_by_id = {}

    for node in nodes:
        status = node.status.value if hasattr(node.status, "value") else str(node.status)
        summary = summary_by_id.get(node.id)
        error = getattr(summary, "error", None) if summary else None
        if status != NodeStatus.online.value and status != "online":
            items.append(
                NocIncidentItem(
                    id=f"node_offline:{node.id}",
                    kind="node_offline",
                    severity="danger",
                    title=f"Узел offline: {node.name}",
                    detail=f"status={status}",
                    at=now,
                    href="/nodes",
                )
            )
        if error:
            role = "прокси-узла" if not _is_vpn_node(node) else "VPN-узла"
            items.append(
                NocIncidentItem(
                    id=f"node_error:{node.id}",
                    kind="node_error",
                    severity="danger",
                    title=f"Ошибка {role}: {node.name}",
                    detail=str(error)[:240],
                    at=now,
                    href="/nodes",
                )
            )
        if summary is not None:
            score = getattr(summary, "health_score", None)
            level = getattr(summary, "health_level", None)
            if level and level != "ok" and status in {NodeStatus.online.value, "online"}:
                role_nom = "Прокси-узел" if not _is_vpn_node(node) else "VPN-узел"
                items.append(
                    NocIncidentItem(
                        id=f"node_unhealthy:{node.id}",
                        kind="node_unhealthy",
                        severity="danger" if level == "critical" else "warning",
                        title=f"{role_nom} нездоров: {node.name}",
                        detail=f"health_score={score} level={level}",
                        at=now,
                        href="/nodes",
                    )
                )

    try:
        active = get_active_node(db)
        active_payload = next((p for p in payloads if p["node"].id == active.id), None)
        if active_payload is not None:
            for service in active_payload.get("services") or []:
                if getattr(service, "active", False):
                    continue
                name = getattr(service, "name", None) or "unknown"
                status = getattr(service, "status", None) or "inactive"
                items.append(
                    NocIncidentItem(
                        id=f"service_down:{active.id}:{name}",
                        kind="service_down",
                        severity="warning",
                        title=f"Служба неактивна: {name}",
                        detail=f"node={active.name} status={status}",
                        at=now,
                        href="/logs",
                    )
                )
    except Exception:
        pass

    cidr_since = now - timedelta(hours=_CIDR_WINDOW_HOURS)
    cidr_rows = (
        db.query(CidrDbRefreshLog)
        .filter(CidrDbRefreshLog.started_at >= cidr_since)
        .order_by(CidrDbRefreshLog.started_at.desc())
        .all()
    )
    for row in cidr_rows:
        status = str(row.status or "")
        if status in {"cleared", "running"}:
            continue
        if status in _CIDR_OK_STATUSES and int(row.providers_failed or 0) == 0:
            continue
        started = _as_naive_utc(row.started_at) or now
        detail_parts = [f"status={status}"]
        if row.providers_failed:
            detail_parts.append(f"providers_failed={row.providers_failed}")
        if row.error:
            detail_parts.append(str(row.error)[:160])
        items.append(
            NocIncidentItem(
                id=f"cidr:{row.id}",
                kind="cidr_failure",
                severity="warning",
                title="Ошибка обновления CIDR",
                detail="; ".join(detail_parts),
                at=started,
                href="/routing",
            )
        )

    items.sort(key=lambda item: item.at, reverse=True)
    return NocIncidentsResponse(items=items[:limit], generated_at=now)
