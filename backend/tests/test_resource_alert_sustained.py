"""Tests for sustained CPU/RAM alert checks against metrics history."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import Node, NodeResourceSample, PanelResourceSample
from app.services.admin_notify import AdminNotifyService
from app.services.resource_alert_sustained import (
    SustainedMetricSource,
    format_alert_details,
    is_sustained_high,
)


def _utcnow() -> datetime:
    return datetime.utcnow()


def test_is_sustained_high_requires_enough_samples(db_session):
    node = Node(name="local", host="127.0.0.1", port=9100, is_local=True)
    db_session.add(node)
    db_session.commit()

    now = _utcnow()
    db_session.add(
        NodeResourceSample(node_id=node.id, cpu_percent=95.0, created_at=now - timedelta(seconds=30))
    )
    db_session.commit()

    ok, detail = is_sustained_high(
        db_session,
        source=SustainedMetricSource.node_cpu,
        node_id=node.id,
        threshold=90.0,
        current_value=95.0,
        sustained_seconds=180,
        sample_interval_seconds=60,
    )
    assert ok is False
    assert detail is None


def test_is_sustained_high_rejects_spike_in_window(db_session):
    node = Node(name="local", host="127.0.0.1", port=9100, is_local=True)
    db_session.add(node)
    db_session.commit()

    now = _utcnow()
    for offset, cpu in [(180, 95.0), (120, 50.0), (60, 96.0), (0, 97.0)]:
        db_session.add(
            NodeResourceSample(
                node_id=node.id,
                cpu_percent=cpu,
                created_at=now - timedelta(seconds=offset),
            )
        )
    db_session.commit()

    ok, detail = is_sustained_high(
        db_session,
        source=SustainedMetricSource.node_cpu,
        node_id=node.id,
        threshold=90.0,
        current_value=97.0,
        sustained_seconds=180,
        sample_interval_seconds=60,
    )
    assert ok is False
    assert detail is None


def test_is_sustained_high_accepts_three_minutes(db_session):
    node = Node(name="local", host="127.0.0.1", port=9100, is_local=True)
    db_session.add(node)
    db_session.commit()

    now = _utcnow()
    for offset, cpu in [(120, 92.0), (60, 94.0), (0, 96.0)]:
        db_session.add(
            NodeResourceSample(
                node_id=node.id,
                cpu_percent=cpu,
                created_at=now - timedelta(seconds=offset),
            )
        )
    db_session.commit()

    ok, detail = is_sustained_high(
        db_session,
        source=SustainedMetricSource.node_cpu,
        node_id=node.id,
        threshold=90.0,
        current_value=96.0,
        sustained_seconds=180,
        sample_interval_seconds=60,
    )
    assert ok is True
    assert detail is not None
    assert "3 замеров" in detail


def test_is_sustained_high_zero_window_skips_history(db_session):
    ok, detail = is_sustained_high(
        db_session,
        source=SustainedMetricSource.node_cpu,
        node_id=1,
        threshold=90.0,
        current_value=95.0,
        sustained_seconds=0,
        sample_interval_seconds=60,
    )
    assert ok is True
    assert detail is None


def test_format_alert_details_includes_sustained():
    text = format_alert_details(96.0, 90.0, "средн. 94.0% за 3 мин (3 замеров)")
    assert "96.0%" in text
    assert "порог 90%" in text
    assert "средн." in text


def test_maybe_send_resource_alert_waits_for_sustained_cpu(db_session):
    node = Node(name="local", host="127.0.0.1", port=9100, is_local=True)
    db_session.add(node)
    db_session.commit()

    now = _utcnow()
    db_session.add(
        NodeResourceSample(node_id=node.id, cpu_percent=100.0, created_at=now - timedelta(seconds=30))
    )
    db_session.commit()

    service = AdminNotifyService()
    with patch.object(service, "send_high_cpu") as send_cpu:
        with patch("app.services.admin_notify.get_feature_service") as feature:
            feature.return_value.is_enabled.return_value = True
            with patch("app.services.admin_notify.get_settings") as settings:
                settings.return_value = MagicMock(
                    monitor_cpu_threshold=90,
                    monitor_ram_threshold=90,
                    monitor_cooldown_minutes=30,
                    monitor_sustained_seconds=180,
                    resource_metrics_interval_seconds=60,
                    monitor_check_interval_seconds=60,
                    panel_resource_metrics_interval_seconds=60,
                )
                service.maybe_send_resource_alert(
                    db_session,
                    cpu_percent=100.0,
                    node_id=node.id,
                    node_name=node.name,
                )
    send_cpu.assert_not_called()


def test_maybe_send_resource_alert_fires_after_sustained_cpu(db_session):
    node = Node(name="local", host="127.0.0.1", port=9100, is_local=True)
    db_session.add(node)
    db_session.commit()

    now = _utcnow()
    for offset in (120, 60, 0):
        db_session.add(
            NodeResourceSample(
                node_id=node.id,
                cpu_percent=95.0,
                created_at=now - timedelta(seconds=offset),
            )
        )
    db_session.commit()

    service = AdminNotifyService()
    with patch.object(service, "send_high_cpu") as send_cpu:
        with patch("app.services.admin_notify.get_feature_service") as feature:
            feature.return_value.is_enabled.return_value = True
            with patch("app.services.admin_notify.get_settings") as settings:
                settings.return_value = MagicMock(
                    monitor_cpu_threshold=90,
                    monitor_ram_threshold=90,
                    monitor_cooldown_minutes=30,
                    monitor_sustained_seconds=180,
                    resource_metrics_interval_seconds=60,
                    monitor_check_interval_seconds=60,
                    panel_resource_metrics_interval_seconds=60,
                )
                service.maybe_send_resource_alert(
                    db_session,
                    cpu_percent=95.0,
                    node_id=node.id,
                    node_name=node.name,
                )
    send_cpu.assert_called_once()
    assert "средн." in send_cpu.call_args.kwargs["details"]


def test_panel_backend_cpu_uses_panel_samples(db_session):
    now = _utcnow()
    for offset in (120, 60, 0):
        db_session.add(
            PanelResourceSample(
                backend_cpu_percent=92.0,
                created_at=now - timedelta(seconds=offset),
            )
        )
    db_session.commit()

    ok, detail = is_sustained_high(
        db_session,
        source=SustainedMetricSource.panel_backend_cpu,
        node_id=None,
        threshold=90.0,
        current_value=92.0,
        sustained_seconds=180,
        sample_interval_seconds=60,
    )
    assert ok is True
    assert detail is not None
