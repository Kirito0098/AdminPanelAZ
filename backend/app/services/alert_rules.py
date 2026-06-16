"""Custom alert rules evaluated against DB aggregates and Prometheus-style metrics."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AlertRule, AlertRuleMetric, AlertRuleOperator, Node, NodeStatus, TrafficSessionState
from app.services.admin_notify import admin_notify_service
from app.services.noc_report import _wg_profile

logger = logging.getLogger(__name__)

ALERT_METRIC_LABELS: dict[str, str] = {
    AlertRuleMetric.ovpn_online_total.value: "OpenVPN online (все узлы)",
    AlertRuleMetric.wg_online_total.value: "WireGuard online (все узлы)",
    AlertRuleMetric.nodes_online.value: "Узлы online",
    AlertRuleMetric.nodes_offline.value: "Узлы offline",
    AlertRuleMetric.node_offline_seconds.value: "Узел offline (сек)",
    AlertRuleMetric.traffic_collector_lag_seconds.value: "Задержка traffic collector (сек)",
}

OPERATOR_LABELS: dict[str, str] = {
    AlertRuleOperator.gt.value: ">",
    AlertRuleOperator.gte.value: "≥",
    AlertRuleOperator.lt.value: "<",
    AlertRuleOperator.lte.value: "≤",
    AlertRuleOperator.eq.value: "=",
}

METRICS_REQUIRING_NODE = frozenset({AlertRuleMetric.node_offline_seconds.value})


def metric_catalog() -> list[dict]:
    return [
        {
            "id": metric_id,
            "label": label,
            "requires_node": metric_id in METRICS_REQUIRING_NODE,
        }
        for metric_id, label in ALERT_METRIC_LABELS.items()
    ]


def _compare(operator: AlertRuleOperator | str, value: float, threshold: float) -> bool:
    op = operator.value if isinstance(operator, AlertRuleOperator) else str(operator)
    if op == AlertRuleOperator.gt.value:
        return value > threshold
    if op == AlertRuleOperator.gte.value:
        return value >= threshold
    if op == AlertRuleOperator.lt.value:
        return value < threshold
    if op == AlertRuleOperator.lte.value:
        return value <= threshold
    if op == AlertRuleOperator.eq.value:
        return value == threshold
    return False


def _session_counts(db: Session) -> tuple[int, int]:
    active_rows = (
        db.query(TrafficSessionState.profile, func.count(TrafficSessionState.id))
        .filter(TrafficSessionState.is_active.is_(True))
        .group_by(TrafficSessionState.profile)
        .all()
    )
    total_ovpn = 0
    total_wg = 0
    for profile, count in active_rows:
        if _wg_profile(profile):
            total_wg += int(count or 0)
        else:
            total_ovpn += int(count or 0)
    return total_ovpn, total_wg


def _traffic_collector_lag_seconds(db: Session) -> float:
    from app.models import UserTrafficSample

    last_sample = db.query(func.max(UserTrafficSample.created_at)).scalar()
    if last_sample is None:
        return -1.0
    if last_sample.tzinfo is None:
        last_sample = last_sample.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return float(max(0, int((now - last_sample).total_seconds())))


def _node_offline_seconds(node: Node, now: datetime) -> float:
    if node.status != NodeStatus.offline:
        return 0.0
    anchor = node.last_seen_at or node.updated_at
    if anchor is None:
        return 0.0
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return float(max(0, int((now - anchor).total_seconds())))


def resolve_metric_value(db: Session, metric: AlertRuleMetric | str, node_id: int | None) -> float | None:
    metric_key = metric.value if isinstance(metric, AlertRuleMetric) else str(metric)
    now = datetime.now(timezone.utc)

    if metric_key == AlertRuleMetric.ovpn_online_total.value:
        ovpn, _ = _session_counts(db)
        return float(ovpn)
    if metric_key == AlertRuleMetric.wg_online_total.value:
        _, wg = _session_counts(db)
        return float(wg)
    if metric_key == AlertRuleMetric.nodes_online.value:
        count = db.query(func.count(Node.id)).filter(Node.status == NodeStatus.online).scalar() or 0
        return float(count)
    if metric_key == AlertRuleMetric.nodes_offline.value:
        count = db.query(func.count(Node.id)).filter(Node.status == NodeStatus.offline).scalar() or 0
        return float(count)
    if metric_key == AlertRuleMetric.traffic_collector_lag_seconds.value:
        return _traffic_collector_lag_seconds(db)
    if metric_key == AlertRuleMetric.node_offline_seconds.value:
        if node_id is not None:
            node = db.query(Node).filter(Node.id == node_id).first()
            if not node:
                return None
            return _node_offline_seconds(node, now)
        offline_nodes = db.query(Node).filter(Node.status == NodeStatus.offline).all()
        if not offline_nodes:
            return 0.0
        return max(_node_offline_seconds(node, now) for node in offline_nodes)

    return None


def format_rule_condition(rule: AlertRule, value: float | None = None) -> str:
    metric_label = ALERT_METRIC_LABELS.get(
        rule.metric.value if hasattr(rule.metric, "value") else str(rule.metric),
        str(rule.metric),
    )
    op_label = OPERATOR_LABELS.get(
        rule.operator.value if hasattr(rule.operator, "value") else str(rule.operator),
        str(rule.operator),
    )
    current = f" (сейчас {value:g})" if value is not None else ""
    return f"{metric_label} {op_label} {rule.threshold:g}{current}"


def _cooldown_active(rule: AlertRule, now: datetime) -> bool:
    if not rule.last_triggered_at:
        return False
    last = rule.last_triggered_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    from datetime import timedelta

    return (now - last) < timedelta(minutes=max(1, int(rule.cooldown_minutes or 1)))


def evaluate_rule(db: Session, rule: AlertRule, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    metric_key = rule.metric.value if hasattr(rule.metric, "value") else str(rule.metric)
    value = resolve_metric_value(db, metric_key, rule.node_id)
    result = {
        "rule_id": rule.id,
        "name": rule.name,
        "metric": metric_key,
        "value": value,
        "threshold": rule.threshold,
        "operator": rule.operator.value if hasattr(rule.operator, "value") else str(rule.operator),
        "triggered": False,
        "skipped_reason": None,
    }
    if not rule.enabled:
        result["skipped_reason"] = "disabled"
        return result
    if value is None:
        result["skipped_reason"] = "metric_unavailable"
        return result
    if not _compare(rule.operator, value, rule.threshold):
        result["skipped_reason"] = "threshold_not_met"
        return result
    if _cooldown_active(rule, now):
        result["skipped_reason"] = "cooldown"
        return result
    result["triggered"] = True
    return result


def notify_rule_trigger(db: Session, rule: AlertRule, value: float) -> None:
    node_name = None
    if rule.node_id is not None:
        node = db.query(Node).filter(Node.id == rule.node_id).first()
        node_name = node.name if node else None
    admin_notify_service.send(
        db,
        "alert_rule",
        target_name=rule.name,
        details=format_rule_condition(rule, value),
        node_id=rule.node_id,
        node_name=node_name,
    )


def evaluate_alert_rules(db: Session, *, notify: bool = True, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rules = db.query(AlertRule).order_by(AlertRule.id.asc()).all()
    results: list[dict] = []
    for rule in rules:
        result = evaluate_rule(db, rule, now=now)
        if result["triggered"]:
            if notify:
                notify_rule_trigger(db, rule, float(result["value"]))
                rule.last_triggered_at = now
        results.append(result)
    if notify:
        db.commit()
    return results


def run_alert_rules_tick(*, notify: bool = True, now: datetime | None = None) -> dict:
    settings = get_settings()
    if not settings.alert_rules_enabled:
        return {"status": "disabled"}

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        results = evaluate_alert_rules(db, notify=notify, now=now)
        triggered = sum(1 for item in results if item.get("triggered"))
        return {"status": "ok", "evaluated": len(results), "triggered": triggered, "results": results}
    except Exception as exc:
        logger.exception("Alert rules tick failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
