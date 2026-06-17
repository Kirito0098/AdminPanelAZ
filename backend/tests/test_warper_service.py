"""Tests for WARPER service layer."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.warper import (
    WarperConflictError,
    WarperNotInstalledError,
    WarperService,
    _build_traffic_chart,
    _normalize_domain,
    detect_warper_installation,
    get_domain_lists_status,
    is_warper_installed,
    run_warper_action,
)


class _FakeResult:
    def __init__(self, ok=True, message="OK", data=None):
        self.ok = ok
        self.message = message
        self.data = data


@pytest.fixture()
def mock_api():
    api = MagicMock()
    api.version = "1.4.0"
    api.is_active.return_value = True
    api.get_status.return_value = _FakeResult(data={"outbound_mode": "warp"})
    api.doctor.return_value = _FakeResult(data=[{"check": "ok", "status": "pass"}])
    api.toggle.return_value = _FakeResult(data={"message": "toggled"})
    api.list_domains.return_value = _FakeResult(data=[{"domain": "example.com"}])
    api.add_domain.return_value = _FakeResult(data={"message": "added"})
    api.remove_domain.return_value = _FakeResult(data={"message": "removed"})
    api.sync_domains.return_value = _FakeResult(data={"message": "synced"})
    return api


def test_is_warper_installed_false():
    with (
        patch("app.services.warper.WARPER_BIN") as bin_path,
        patch("app.services.warper.WARPER_SCRIPT") as script_path,
        patch("app.services.warper.WARPER_API_INIT") as init_path,
    ):
        bin_path.is_file.return_value = False
        script_path.is_file.return_value = False
        init_path.is_file.return_value = False
        assert is_warper_installed() is False


def test_detect_warper_installation_script_without_symlink():
    with (
        patch("app.services.warper.WARPER_BIN") as bin_path,
        patch("app.services.warper.WARPER_SCRIPT") as script_path,
        patch("app.services.warper.WARPER_API_INIT") as init_path,
    ):
        bin_path.is_file.return_value = False
        script_path.is_file.return_value = True
        init_path.is_file.return_value = True
        detection = detect_warper_installation()
        assert detection["installed"] is True
        assert "warper_symlink" in detection["missing_components"]


def test_normalize_domain_valid():
    assert _normalize_domain("Example.COM") == "example.com"
    assert _normalize_domain("*.cdn.example.com") == "cdn.example.com"


def test_normalize_domain_invalid():
    with pytest.raises(HTTPException) as exc:
        _normalize_domain("not a domain")
    assert exc.value.status_code == 400


def test_get_health_not_installed():
    service = WarperService()
    with patch("app.services.warper.is_warper_installed", return_value=False):
        with patch("app.services.warper._has_antizapret_warp_conflict", return_value=False):
            health = service.get_health()
    assert health["installed"] is False
    assert health["active"] is False


def test_get_health_installed(mock_api):
    service = WarperService()
    with (
        patch(
            "app.services.warper.detect_warper_installation",
            return_value={
                "installed": True,
                "warper_bin": True,
                "warper_script": True,
                "warper_api": True,
                "missing_components": [],
            },
        ),
        patch("app.services.warper._has_antizapret_warp_conflict", return_value=False),
        patch.object(service, "_api_client", return_value=mock_api),
    ):
        health = service.get_health()
    assert health["installed"] is True
    assert health["active"] is True
    assert health["version"] == "1.4.0"


def test_get_status_not_installed():
    service = WarperService()
    with patch("app.services.warper._ensure_installed", side_effect=WarperNotInstalledError("no warper")):
        with pytest.raises(WarperNotInstalledError):
            service.get_status()


def test_add_domain_conflict():
    service = WarperService()
    with (
        patch("app.services.warper._ensure_no_conflict", side_effect=WarperConflictError("conflict")),
        patch("app.services.warper._ensure_installed"),
    ):
        with pytest.raises(WarperConflictError):
            service.add_domain("example.com")


def test_add_domain_success(mock_api):
    service = WarperService()
    with (
        patch("app.services.warper._ensure_no_conflict"),
        patch.object(service, "_api_client", return_value=mock_api),
    ):
        result = service.add_domain("example.com")
    assert result["message"] == "added"
    mock_api.add_domain.assert_called_once_with("example.com")


def test_list_domains_api_failure(mock_api):
    mock_api.list_domains.return_value = _FakeResult(ok=False, message="fail")
    service = WarperService()
    with (
        patch.object(service, "_api_client", return_value=mock_api),
        patch("app.services.warper._parse_domains_file", return_value=[]),
    ):
        result = service.list_domains()
    assert result == []


def test_run_warper_action_not_installed():
    with patch("app.services.warper.WarperService.get_health", side_effect=WarperNotInstalledError("x")):
        with pytest.raises(HTTPException) as exc:
            run_warper_action("status")
    assert exc.value.status_code == 503


def test_run_warper_action_conflict():
    with patch("app.services.warper.WarperService.add_domain", side_effect=WarperConflictError("x")):
        with pytest.raises(HTTPException) as exc:
            run_warper_action("add_domain", domain="a.com")
    assert exc.value.status_code == 409


def test_get_mode_accepts_plain_string(mock_api):
    mock_api.get_mode.return_value = "warp"
    mock_api.get_mtu.return_value = 1420
    mock_api.get_log_level.return_value = "info"
    service = WarperService()
    with patch.object(service, "_api_client", return_value=mock_api):
        mode = service.get_mode()
    assert mode["outbound_mode"] == "warp"
    assert mode["mtu"] == 1420
    assert mode["log_level"] == "info"


def test_doctor_returns_checks_when_cli_fails(mock_api):
    mock_api.doctor.return_value = _FakeResult(
        ok=False,
        message="==========================================\n 🩺 WARPER DOCTOR\n... (34 строк всего)",
        data=[
            {"status": "ok", "text": "ANTIZAPRET_WARP=n"},
            {"status": "error", "text": "Служба sing-box активна"},
        ],
    )
    service = WarperService()
    with patch.object(service, "_api_client", return_value=mock_api):
        items = service.doctor()
    assert len(items) == 2
    assert items[0]["status"] == "ok"
    assert items[1]["status"] == "error"


def test_get_domain_lists_status_from_markers(tmp_path):
    domains_file = tmp_path / "domains.txt"
    domains_file.write_text(
        "# Пользовательские домены:\n"
        "example.com\n\n"
        "# --- GEMINI ---\n"
        "gemini.google.com\n"
        "# --- END GEMINI ---\n",
        encoding="utf-8",
    )
    with patch("app.services.warper.WARPER_DOMAINS_FILE", domains_file):
        status = get_domain_lists_status()
    assert status == {"gemini": True, "chatgpt": False}


def test_list_ip_ranges_fallback_to_file(mock_api, tmp_path):
    mock_api.list_ip_ranges.return_value = _FakeResult(ok=False, message="iplist failed")
    ip_file = tmp_path / "ip-ranges.txt"
    ip_file.write_text("91.108.4.0/22\n# comment\n", encoding="utf-8")
    service = WarperService()
    with (
        patch.object(service, "_api_client", return_value=mock_api),
        patch("app.services.warper.WARPER_IP_RANGES_FILE", ip_file),
    ):
        ranges = service.list_ip_ranges()
    assert ranges == ["91.108.4.0/22"]


def test_get_user_domains_text_uses_api(mock_api):
    mock_api.get_user_domains_text.return_value = "# user\nexample.com\n"
    service = WarperService()
    with patch.object(service, "_api_client", return_value=mock_api):
        text = service.get_user_domains_text()
    assert "example.com" in text


def test_save_user_domains_text_calls_api(mock_api):
    mock_api.save_user_domains_text.return_value = _FakeResult(data={"message": "saved"})
    service = WarperService()
    with (
        patch("app.services.warper._ensure_no_conflict"),
        patch.object(service, "_api_client", return_value=mock_api),
    ):
        result = service.save_user_domains_text("example.com\n")
    assert result["message"] == "saved"
    mock_api.save_user_domains_text.assert_called_once_with("example.com\n")


def test_get_ip_ranges_text_fallback_to_file(mock_api, tmp_path):
    ip_file = tmp_path / "ip-ranges.txt"
    ip_file.write_text("10.0.0.0/8\n", encoding="utf-8")
    service = WarperService()
    with (
        patch.object(service, "_api_client", return_value=mock_api),
        patch("app.services.warper.WARPER_IP_RANGES_FILE", ip_file),
    ):
        del mock_api.get_ip_ranges_text
        text = service.get_ip_ranges_text()
    assert text == "10.0.0.0/8\n"


def test_set_mode_warp_with_key_source(mock_api):
    mock_api.set_mode_warp.return_value = _FakeResult(data={"message": "warp"})
    service = WarperService()
    with (
        patch("app.services.warper._ensure_no_conflict"),
        patch.object(service, "_api_client", return_value=mock_api),
    ):
        service.set_mode_warp("system")
    mock_api.set_mode_warp.assert_called_once_with("system")


def test_build_traffic_chart_today_hourly(tmp_path):
    traffic_file = tmp_path / "traffic.json"
    traffic_file.write_text(
        json.dumps(
            {
                "hourly": {
                    "2026-06-17T10": {"rx": 1000, "tx": 2000},
                    "2026-06-17T11": {"rx": 500, "tx": 700},
                    "2026-06-16T23": {"rx": 999, "tx": 999},
                }
            }
        ),
        encoding="utf-8",
    )
    with (
        patch("app.services.warper.WARPER_TRAFFIC_FILE", traffic_file),
        patch("app.services.warper.datetime") as mocked_dt,
    ):
        mocked_dt.now.return_value = __import__("datetime").datetime(2026, 6, 17, 12, 0, tzinfo=__import__("datetime").timezone.utc)
        mocked_dt.strptime = __import__("datetime").datetime.strptime
        mocked_dt.side_effect = lambda *args, **kwargs: __import__("datetime").datetime(*args, **kwargs)
        chart = _build_traffic_chart("today")
    assert chart == [
        {"label": "10:00", "rx": 1000, "tx": 2000},
        {"label": "11:00", "rx": 500, "tx": 700},
    ]


def test_get_traffic_includes_chart(mock_api, tmp_path):
    traffic_file = tmp_path / "traffic.json"
    traffic_file.write_text(
        json.dumps({"hourly": {"2026-06-17T09": {"rx": 10, "tx": 20}}}),
        encoding="utf-8",
    )
    mock_api.get_traffic.return_value = _FakeResult(
        data={"period_rx": 10, "period_tx": 20, "period": "today"},
    )
    service = WarperService()
    with (
        patch("app.services.warper.WARPER_TRAFFIC_FILE", traffic_file),
        patch("app.services.warper.datetime") as mocked_dt,
        patch.object(service, "_api_client", return_value=mock_api),
    ):
        mocked_dt.now.return_value = __import__("datetime").datetime(2026, 6, 17, 12, 0, tzinfo=__import__("datetime").timezone.utc)
        mocked_dt.strptime = __import__("datetime").datetime.strptime
        mocked_dt.side_effect = lambda *args, **kwargs: __import__("datetime").datetime(*args, **kwargs)
        payload = service.get_traffic("today")
    assert payload["period_rx"] == 10
    assert payload["chart"]


def test_singbox_action_via_api(mock_api):
    mock_api.singbox_restart.return_value = _FakeResult(message="sing-box restart: ok")
    service = WarperService()
    with (
        patch("app.services.warper._ensure_no_conflict"),
        patch.object(service, "_api_client", return_value=mock_api),
    ):
        result = service.singbox_action("restart")
    assert result["success"] is True
    mock_api.singbox_restart.assert_called_once()


def test_singbox_action_api_failure_raises_502(mock_api):
    mock_api.singbox_restart.return_value = _FakeResult(ok=False, message="sing-box restart: ошибка (unit failed)")
    service = WarperService()
    with (
        patch("app.services.warper._ensure_no_conflict"),
        patch.object(service, "_api_client", return_value=mock_api),
    ):
        with pytest.raises(HTTPException) as exc:
            service.singbox_action("restart")
    assert exc.value.status_code == 502
    assert "ошибка" in str(exc.value.detail).lower()


def test_singbox_action_systemctl_fallback():
    service = WarperService()
    fake_proc = MagicMock(returncode=0, stdout="", stderr="")
    with (
        patch("app.services.warper._ensure_no_conflict"),
        patch.object(service, "_api_client", side_effect=AttributeError("singbox_restart")),
        patch("app.services.warper.subprocess.run", return_value=fake_proc) as run_mock,
    ):
        result = service.singbox_action("restart")
    assert result["success"] is True
    run_mock.assert_called_once_with(
        ["systemctl", "restart", "sing-box"],
        capture_output=True,
        text=True,
        timeout=90,
    )


def test_run_warper_action_singbox_dispatch():
    service = WarperService()
    with patch("app.services.warper.WarperService", return_value=service):
        with patch.object(
            service,
            "singbox_action",
            return_value={"message": "ok", "success": True},
        ) as singbox_mock:
            result = run_warper_action("singbox_action", action="restart")
    assert result["success"] is True
    singbox_mock.assert_called_once_with("restart")


def test_run_warper_action_unknown_error_returns_502():
    service = WarperService()
    with patch("app.services.warper.WarperService", return_value=service):
        with patch.object(service, "singbox_action", side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc:
                run_warper_action("singbox_action", action="restart")
    assert exc.value.status_code == 502
    assert "boom" in str(exc.value.detail)
