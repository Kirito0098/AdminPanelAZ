"""Tests for custom alert rules (7.3)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models import (
    AlertRule,
    AlertRuleMetric,
    AlertRuleOperator,
    AppSetting,
    Node,
    NodeStatus,
    TrafficSessionState,
    User,
    UserRole,
)
from app.services.alert_rules import (
    evaluate_alert_rules,
    evaluate_rule,
    resolve_metric_value,
    run_alert_rules_tick,
)


def _seed_ovpn_sessions(db_session, count: int, *, node_id: int = 1) -> None:
    for idx in range(count):
        db_session.add(
            TrafficSessionState(
                node_id=node_id,
                session_key=f"ovpn-{idx}",
                profile="openvpn",
                common_name=f"client-{idx}",
                is_active=True,
            )
        )
    db_session.commit()


def test_resolve_ovpn_online_total(db_session):
    db_session.add(Node(id=1, name="eu-1", host="10.0.0.1", status=NodeStatus.online))
    _seed_ovpn_sessions(db_session, 3)
    value = resolve_metric_value(db_session, AlertRuleMetric.ovpn_online_total, None)
    assert value == 3.0


def test_evaluate_rule_triggers_when_threshold_exceeded(db_session):
    db_session.add(Node(id=1, name="eu-1", host="10.0.0.1", status=NodeStatus.online))
    _seed_ovpn_sessions(db_session, 55)
    rule = AlertRule(
        name="OVPN online > 50",
        metric=AlertRuleMetric.ovpn_online_total,
        operator=AlertRuleOperator.gt,
        threshold=50,
        cooldown_minutes=30,
        enabled=True,
    )
    db_session.add(rule)
    db_session.commit()

    result = evaluate_rule(db_session, rule)
    assert result["triggered"] is True
    assert result["value"] == 55.0


def test_evaluate_rule_respects_cooldown(db_session):
    db_session.add(Node(id=1, name="eu-1", host="10.0.0.1", status=NodeStatus.online))
    _seed_ovpn_sessions(db_session, 55)
    rule = AlertRule(
        name="OVPN online > 50",
        metric=AlertRuleMetric.ovpn_online_total,
        operator=AlertRuleOperator.gt,
        threshold=50,
        cooldown_minutes=30,
        enabled=True,
        last_triggered_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add(rule)
    db_session.commit()

    result = evaluate_rule(db_session, rule)
    assert result["triggered"] is False
    assert result["skipped_reason"] == "cooldown"


def test_node_offline_seconds_triggers(db_session):
    offline_since = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.add(
        Node(
            id=1,
            name="eu-1",
            host="10.0.0.1",
            status=NodeStatus.offline,
            last_seen_at=offline_since,
        )
    )
    rule = AlertRule(
        name="Node offline > 5 min",
        metric=AlertRuleMetric.node_offline_seconds,
        operator=AlertRuleOperator.gt,
        threshold=300,
        node_id=1,
        cooldown_minutes=15,
        enabled=True,
    )
    db_session.add(rule)
    db_session.commit()

    value = resolve_metric_value(db_session, AlertRuleMetric.node_offline_seconds, 1)
    assert value is not None
    assert value >= 600

    result = evaluate_rule(db_session, rule)
    assert result["triggered"] is True


def test_evaluate_alert_rules_sends_admin_notify(db_session):
    db_session.add_all(
        [
            AppSetting(key="telegram_notify_enabled", value="true"),
            AppSetting(key="telegram_bot_token", value="test-token"),
        ]
    )
    admin = User(
        username="admin",
        password_hash="x",
        role=UserRole.admin,
        telegram_id="12345",
        tg_notify_events='{"alert_rule": true}',
    )
    db_session.add(admin)
    db_session.add(Node(id=1, name="eu-1", host="10.0.0.1", status=NodeStatus.online))
    _seed_ovpn_sessions(db_session, 60)
    rule = AlertRule(
        name="OVPN online > 50",
        metric=AlertRuleMetric.ovpn_online_total,
        operator=AlertRuleOperator.gt,
        threshold=50,
        cooldown_minutes=30,
        enabled=True,
    )
    db_session.add(rule)
    db_session.commit()

    with patch("app.services.admin_notify.send_tg_message") as send_mock:
        with patch("app.services.admin_notify.get_feature_service") as feature_mock:
            feature_mock.return_value.is_enabled.return_value = True
            results = evaluate_alert_rules(db_session, notify=True)

    assert results[0]["triggered"] is True
    send_mock.assert_called_once()
    text = send_mock.call_args[0][2]
    assert "OVPN online > 50" in text
    assert "Alert rule" in text


def test_run_alert_rules_tick_disabled(monkeypatch):
    from app.config import Settings, get_settings

    monkeypatch.setenv("ALERT_RULES_ENABLED", "false")
    get_settings.cache_clear()
    try:
        result = run_alert_rules_tick()
        assert result["status"] == "disabled"
    finally:
        get_settings.cache_clear()


def test_alert_rules_api_crud(api_test_env):
    from fastapi.testclient import TestClient

    env = api_test_env
    client = TestClient(env["app"])
    session = env["session_factory"]()
    session.add(
        Node(
            name="remote",
            host="10.0.0.2",
            port=9100,
            status=NodeStatus.online,
        )
    )
    session.commit()
    node_id = session.query(Node).filter(Node.name == "remote").first().id
    session.close()

    create_resp = client.post(
        "/api/alert-rules",
        headers=env["admin_headers"],
        json={
            "name": "OVPN online > 50",
            "metric": "ovpn_online_total",
            "operator": "gt",
            "threshold": 50,
            "cooldown_minutes": 30,
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["name"] == "OVPN online > 50"
    rule_id = body["id"]

    list_resp = client.get("/api/alert-rules", headers=env["admin_headers"])
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    viewer_resp = client.get("/api/alert-rules", headers=env["viewer_headers"])
    assert viewer_resp.status_code == 403

    patch_resp = client.patch(
        f"/api/alert-rules/{rule_id}",
        headers=env["admin_headers"],
        json={"enabled": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["enabled"] is False

    delete_resp = client.delete(
        f"/api/alert-rules/{rule_id}",
        headers=env["admin_headers"],
    )
    assert delete_resp.status_code == 200

    metrics_resp = client.get("/api/alert-rules/metrics", headers=env["admin_headers"])
    assert metrics_resp.status_code == 200
    metrics = {item["id"] for item in metrics_resp.json()}
    assert "ovpn_online_total" in metrics
    assert "node_offline_seconds" in metrics

    offline_rule = client.post(
        "/api/alert-rules",
        headers=env["admin_headers"],
        json={
            "name": "Node offline > 5 min",
            "metric": "node_offline_seconds",
            "operator": "gt",
            "threshold": 300,
            "node_id": node_id,
        },
    )
    assert offline_rule.status_code == 201

    missing_node = client.post(
        "/api/alert-rules",
        headers=env["admin_headers"],
        json={
            "name": "bad",
            "metric": "node_offline_seconds",
            "operator": "gt",
            "threshold": 300,
        },
    )
    assert missing_node.status_code == 400
