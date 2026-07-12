"""Unit tests for sustained node offline AdminNotify (grace timeout)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.models import NodeStatus
from app.services import node_status_notify as nsn
from app.services.node_status_notify import (
    ALERT_SENT_META_KEY,
    OFFLINE_SINCE_META_KEY,
    clamp_grace_seconds,
    evaluate_node_offline_notify,
)


def _make_node(
    *,
    node_id: int = 1,
    name: str = "RU-1",
    host: str = "10.0.0.1",
    port: int = 9100,
    last_seen_at: datetime | None = None,
    metadata: dict | None = None,
):
    node = MagicMock()
    node.id = node_id
    node.name = name
    node.host = host
    node.port = port
    node.last_seen_at = last_seen_at
    node.node_metadata = json.dumps(metadata or {})
    return node


def test_clamp_grace_seconds():
    assert clamp_grace_seconds(30) == 60
    assert clamp_grace_seconds(180) == 180
    assert clamp_grace_seconds(999999) == 86400
    assert clamp_grace_seconds("nope") == 180


@patch("app.services.node_status_notify.get_node_offline_grace_seconds", return_value=180)
@patch("app.services.node_status_notify.admin_notify_service")
@patch("app.services.node_status_notify.log_action")
def test_offline_below_grace_no_alert(mock_log_action, mock_notify, _grace):
    db = MagicMock()
    now = datetime.now(timezone.utc)
    node = _make_node(last_seen_at=now - timedelta(seconds=30))
    evaluate_node_offline_notify(
        db,
        node,
        prev_status=NodeStatus.online,
        new_status=NodeStatus.offline,
        error="timeout",
    )
    mock_log_action.assert_not_called()
    mock_notify.send_node_offline.assert_not_called()
    meta = json.loads(node.node_metadata)
    assert OFFLINE_SINCE_META_KEY in meta
    assert ALERT_SENT_META_KEY not in meta


@patch("app.services.node_status_notify.get_node_offline_grace_seconds", return_value=180)
@patch("app.services.node_status_notify.admin_notify_service")
@patch("app.services.node_status_notify.log_action")
def test_offline_past_grace_alerts_once(mock_log_action, mock_notify, _grace):
    db = MagicMock()
    now = datetime.now(timezone.utc)
    node = _make_node(last_seen_at=now - timedelta(seconds=200))
    evaluate_node_offline_notify(
        db,
        node,
        prev_status=NodeStatus.online,
        new_status=NodeStatus.offline,
        error="Connection refused",
    )
    mock_log_action.assert_called_once()
    assert mock_log_action.call_args.kwargs["action"] == "node_offline"
    mock_notify.send_node_offline.assert_called_once()
    meta = json.loads(node.node_metadata)
    assert meta.get(ALERT_SENT_META_KEY) is True

    mock_log_action.reset_mock()
    mock_notify.reset_mock()
    evaluate_node_offline_notify(
        db,
        node,
        prev_status=NodeStatus.offline,
        new_status=NodeStatus.offline,
        error="Connection refused",
    )
    mock_log_action.assert_not_called()
    mock_notify.send_node_offline.assert_not_called()


@patch("app.services.node_status_notify.admin_notify_service")
@patch("app.services.node_status_notify.log_action")
def test_online_after_alert_sends_recovery(mock_log_action, mock_notify):
    db = MagicMock()
    node = _make_node(
        metadata={ALERT_SENT_META_KEY: True, OFFLINE_SINCE_META_KEY: "2026-01-01T00:00:00+00:00"},
    )
    evaluate_node_offline_notify(
        db,
        node,
        prev_status=NodeStatus.offline,
        new_status=NodeStatus.online,
    )
    mock_log_action.assert_called_once()
    assert mock_log_action.call_args.kwargs["action"] == "node_online"
    mock_notify.send_node_online.assert_called_once()
    meta = json.loads(node.node_metadata)
    assert ALERT_SENT_META_KEY not in meta
    assert OFFLINE_SINCE_META_KEY not in meta


@patch("app.services.node_status_notify.admin_notify_service")
@patch("app.services.node_status_notify.log_action")
def test_online_without_prior_alert_no_recovery(mock_log_action, mock_notify):
    db = MagicMock()
    node = _make_node(metadata={OFFLINE_SINCE_META_KEY: "2026-01-01T00:00:00+00:00"})
    evaluate_node_offline_notify(
        db,
        node,
        prev_status=NodeStatus.offline,
        new_status=NodeStatus.online,
    )
    mock_log_action.assert_not_called()
    mock_notify.send_node_online.assert_not_called()
    meta = json.loads(node.node_metadata)
    assert OFFLINE_SINCE_META_KEY not in meta


@patch("app.services.node_status_notify.evaluate_node_offline_notify")
def test_update_node_from_health_calls_evaluate(mock_evaluate):
    from app.services.node_manager import update_node_from_health

    db = MagicMock()
    node = _make_node()
    node.status = NodeStatus.online
    node.node_metadata = "{}"
    node.last_seen_at = None
    node.updated_at = None

    update_node_from_health(node, {"status": "offline", "error": "boom"}, db)

    assert node.status == NodeStatus.offline
    db.commit.assert_called()
    mock_evaluate.assert_called_once()
    kwargs = mock_evaluate.call_args.kwargs
    assert kwargs["prev_status"] == NodeStatus.online
    assert kwargs["new_status"] == NodeStatus.offline
    assert kwargs["error"] == "boom"


def test_notify_alias_points_to_evaluate():
    assert nsn.notify_node_status_transition is nsn.evaluate_node_offline_notify
