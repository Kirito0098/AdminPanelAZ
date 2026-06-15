"""Tests for NOC scheduled report builder and scheduler."""

from datetime import datetime, timezone
from unittest.mock import patch

from app.config import Settings
from app.models import AppSetting, Node, NodeStatus, TrafficSessionState, User, UserRole
from app.services.cron_schedule import cron_matches_now, cron_weekday_value
from app.services.noc_report import build_noc_summary, format_noc_report_message, send_noc_report
from app.services.noc_report_scheduler import run_noc_report_once, run_noc_report_scheduler_tick


def test_cron_matches_weekly_monday():
    monday = datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc)
    assert cron_weekday_value(monday) == 1
    assert cron_matches_now("0 9 * * 1", monday) is True
    assert cron_matches_now("0 9 * * 1", monday.replace(minute=1)) is False


def test_build_noc_summary_aggregates_sessions(db_session):
    db_session.add_all(
        [
            Node(id=1, name="eu-1", host="10.0.0.1", status=NodeStatus.online),
            Node(id=2, name="us-1", host="10.0.0.2", status=NodeStatus.offline),
        ]
    )
    db_session.add_all(
        [
            TrafficSessionState(
                node_id=1,
                session_key="ovpn-1",
                profile="openvpn",
                common_name="client-a",
                is_active=True,
            ),
            TrafficSessionState(
                node_id=1,
                session_key="wg-1",
                profile="client-b-wg",
                common_name="client-b",
                is_active=True,
            ),
            TrafficSessionState(
                node_id=2,
                session_key="ovpn-2",
                profile="openvpn",
                common_name="client-c",
                is_active=False,
            ),
        ]
    )
    db_session.commit()

    summary = build_noc_summary(db_session)
    assert summary["nodes_total"] == 2
    assert summary["nodes_online"] == 1
    assert summary["total_openvpn"] == 1
    assert summary["total_wireguard"] == 1
    assert summary["nodes"][0]["name"] == "eu-1"
    assert summary["nodes"][1]["status"] == NodeStatus.offline.value


def test_format_noc_report_message_contains_counts(db_session):
    summary = {
        "nodes_online": 1,
        "nodes_total": 2,
        "total_openvpn": 3,
        "total_wireguard": 1,
        "total_traffic_bytes": 1024 * 1024,
        "nodes": [{"name": "eu-1", "status": "online", "openvpn": 3, "wireguard": 1}],
    }
    text = format_noc_report_message(summary, period="daily")
    assert "NOC сводка" in text
    assert "OVPN <b>3</b>" in text
    assert "eu-1" in text


def test_send_noc_report_delivers_to_admin(db_session):
    admin = User(
        username="admin",
        password_hash="x",
        role=UserRole.admin,
        telegram_id="12345",
        tg_notify_events='{"noc_report": true}',
    )
    db_session.add(admin)
    db_session.add_all(
        [
            AppSetting(key="telegram_notify_enabled", value="true"),
            AppSetting(key="telegram_bot_token", value="bot-token"),
        ]
    )
    db_session.commit()

    with (
        patch("app.services.noc_report.get_feature_service") as mock_features,
        patch("app.services.noc_report.send_tg_message", return_value=True) as mock_send,
        patch("app.services.noc_report.build_noc_summary", return_value={"nodes_online": 1, "nodes_total": 1, "total_openvpn": 0, "total_wireguard": 0, "total_traffic_bytes": 0, "nodes": []}),
    ):
        mock_features.return_value.is_enabled.return_value = True
        result = send_noc_report(db_session, period="daily")

    assert result["status"] == "sent"
    assert result["sent"] == 1
    mock_send.assert_called_once()


def test_run_noc_report_once_skips_when_disabled():
    with patch("app.services.noc_report_scheduler.get_settings") as mock_settings:
        mock_settings.return_value = Settings(noc_report_enabled=False)
        result = run_noc_report_once(period="daily", cron_expr="0 8 * * *")
    assert result["status"] == "disabled"


def test_run_noc_report_scheduler_tick_sends_daily(db_session):
    admin = User(
        username="admin",
        password_hash="x",
        role=UserRole.admin,
        telegram_id="999",
        tg_notify_events='{"noc_report": true}',
    )
    db_session.add(admin)
    db_session.add_all(
        [
            AppSetting(key="telegram_notify_enabled", value="true"),
            AppSetting(key="telegram_bot_token", value="token"),
        ]
    )
    db_session.commit()

    fixed_now = datetime(2026, 6, 16, 8, 0, tzinfo=timezone.utc)
    settings = Settings(
        noc_report_enabled=True,
        noc_report_daily_cron="0 8 * * *",
        noc_report_weekly_cron="0 9 * * 1",
    )

    with (
        patch("app.services.noc_report_scheduler.get_settings", return_value=settings),
        patch("app.services.noc_report_scheduler.SessionLocal", lambda: db_session),
        patch("app.services.noc_report.get_feature_service") as mock_features,
        patch("app.services.noc_report.send_tg_message", return_value=True),
    ):
        mock_features.return_value.is_enabled.return_value = True
        results = run_noc_report_scheduler_tick(now=fixed_now)

    daily = next(item for item in results if item.get("period") == "daily")
    weekly = next(item for item in results if item.get("period") == "weekly")
    assert daily["status"] == "sent"
    assert weekly["status"] == "skipped"
