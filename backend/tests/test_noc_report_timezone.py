from datetime import datetime, timezone

from app.services.noc_report import (
    _format_incident_line,
    _format_period_window,
    format_noc_report_message,
)


def test_weekly_window_moscow_not_utc_literal():
    since = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    until = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)

    text = _format_period_window(since, until, period="weekly", tz_name="Europe/Moscow")

    assert "UTC" not in text
    assert "MSK" in text or "UTC+3" in text


def test_incident_line_moscow_hour():
    line = _format_incident_line(
        {
            "name": "CPU",
            "last_triggered_at": datetime(2026, 9, 7, 8, 56, tzinfo=timezone.utc),
        },
        tz_name="Europe/Moscow",
    )

    assert "11:56" in line


def test_format_noc_report_message_uses_client_timezone():
    text = format_noc_report_message(
        {
            "period": "weekly",
            "period_start": datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
            "period_end": datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc),
            "summary": {
                "nodes_online": 1,
                "nodes_total": 1,
                "total_openvpn": 0,
                "total_wireguard": 0,
                "total_amneziawg2": 0,
                "total_openvpn_peak": 0,
                "total_wireguard_peak": 0,
                "total_amneziawg2_peak": 0,
                "awg2_enabled": False,
                "nodes": [],
            },
            "incidents": [
                {
                    "name": "CPU",
                    "last_triggered_at": datetime(2026, 9, 7, 8, 56, tzinfo=timezone.utc),
                }
            ],
        },
        client_timezone="Europe/Moscow",
    )

    assert "UTC" not in text
    assert "11:56" in text
