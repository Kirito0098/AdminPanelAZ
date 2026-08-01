"""Per-recipient send APIs for NOC reports."""

from types import SimpleNamespace
from unittest.mock import MagicMock


def test_send_noc_report_honors_explicit_recipients(monkeypatch):
    from app.services import noc_report

    user = SimpleNamespace(id=1, telegram_id="111", timezone="Europe/Moscow", last_client_timezone="")
    sent: list[str] = []
    monkeypatch.setattr(noc_report, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda k: True))
    monkeypatch.setattr(noc_report, "_get_setting", lambda db, k, d="": "true" if "enabled" in k else "token")
    monkeypatch.setattr(noc_report, "build_noc_report_data", lambda db, period="daily": {"period": period, "summary": {
        "nodes_online": 1, "nodes_total": 1, "total_openvpn": 0, "total_wireguard": 0,
        "total_openvpn_peak": 0, "total_wireguard_peak": 0,
    }})
    monkeypatch.setattr(noc_report, "format_noc_report_message", lambda data, client_timezone=None: "TEXT")
    monkeypatch.setattr(noc_report, "send_tg_message", lambda token, chat_id, text, **kw: sent.append(chat_id) or True)
    monkeypatch.setattr(noc_report, "_notify_recipients", lambda db: (_ for _ in ()).throw(AssertionError("should not call")))

    db = MagicMock()
    result = noc_report.send_noc_report(db, period="daily", recipients=[user])
    assert result["status"] == "sent"
    assert sent == ["111"]


def test_send_weekly_image_report_honors_explicit_recipients(monkeypatch):
    from app.services import noc_report

    user = SimpleNamespace(id=1, telegram_id="222", timezone="Europe/Moscow", last_client_timezone="")
    sent: list[str] = []
    monkeypatch.setattr(
        noc_report,
        "get_settings",
        lambda: SimpleNamespace(
            noc_report_weekly_image_enabled=True,
            noc_report_weekly_image_tg_enabled=True,
        ),
    )
    monkeypatch.setattr(noc_report, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda k: True))
    monkeypatch.setattr(noc_report, "_get_setting", lambda db, k, d="": "true" if "enabled" in k else "token")
    monkeypatch.setattr(noc_report, "generate_weekly_image_bytes", lambda db, since=None, until=None: b"PNG")
    monkeypatch.setattr(
        noc_report,
        "send_tg_photo",
        lambda token, chat_id, path, **kw: sent.append(chat_id) or True,
    )
    monkeypatch.setattr(noc_report, "_notify_recipients", lambda db: (_ for _ in ()).throw(AssertionError("should not call")))

    db = MagicMock()
    result = noc_report.send_weekly_image_report(db, recipients=[user])
    assert result["status"] == "sent"
    assert sent == ["222"]
