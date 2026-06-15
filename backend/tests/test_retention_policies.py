"""Tests for retention purge policies."""

from datetime import datetime, timedelta

from app.models import Node, NodeResourceSample, NodeStatus, PanelResourceSample, UserActionLog, UserTrafficSample
from app.services.retention import run_retention_purge


def test_retention_purge_removes_old_rows(db_session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("TRAFFIC_SAMPLE_RETENTION_DAYS", "30")
    monkeypatch.setenv("ACTION_LOG_RETENTION_DAYS", "30")
    monkeypatch.setenv("RESOURCE_METRICS_RETENTION_DAYS", "30")
    monkeypatch.setenv("PANEL_RESOURCE_METRICS_RETENTION_DAYS", "30")
    get_settings.cache_clear()

    old = datetime.utcnow() - timedelta(days=40)
    recent = datetime.utcnow() - timedelta(days=1)

    db_session.add(Node(id=1, name="test-node", host="127.0.0.1", status=NodeStatus.online))
    db_session.flush()

    db_session.add(
        UserTrafficSample(
            node_id=1,
            common_name="client-a",
            created_at=old,
        )
    )
    db_session.add(
        UserTrafficSample(
            node_id=1,
            common_name="client-b",
            created_at=recent,
        )
    )
    db_session.add(UserActionLog(action="test", created_at=old))
    db_session.add(UserActionLog(action="keep", created_at=recent))
    db_session.add(NodeResourceSample(node_id=1, created_at=old))
    db_session.add(PanelResourceSample(created_at=old))
    db_session.commit()

    counts = run_retention_purge(db_session)

    assert counts["user_traffic_sample"] == 1
    assert counts["user_action_log"] == 1
    assert counts["node_resource_sample"] == 1
    assert counts["panel_resource_sample"] == 1
    assert db_session.query(UserTrafficSample).count() == 1
    assert db_session.query(UserActionLog).count() == 1
