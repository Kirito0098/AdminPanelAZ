"""Tests for scripts/safe-browsing-status.py (ported from AdminAntizapret)."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import urllib.error

ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "scripts" / "safe-browsing-status.py"


def _load_cli_module():
    spec = importlib.util.spec_from_file_location("safe_browsing_status_cli", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["safe_browsing_status_cli"] = module
    spec.loader.exec_module(module)
    return module


cli = _load_cli_module()


def test_parse_status_payload_extracts_threat_flag():
    raw = (
        ")]}'\n\n"
        '[["sb.ssr",2,false,false,true,false,false,1779153594802,"admin.vpn.claymore-it.ru"]]\n'
    )
    parsed = cli.parse_status_payload(raw)
    assert parsed["site"] == "admin.vpn.claymore-it.ru"
    assert parsed["status_code"] == 2
    assert parsed["threat_flag"] is True


def test_parse_status_payload_for_safe_site():
    raw = (
        ")]}'\n\n"
        '[["sb.ssr",4,false,false,false,false,false,1767633340523,"google.com"]]\n'
    )
    parsed = cli.parse_status_payload(raw)
    assert parsed["site"] == "google.com"
    assert parsed["status_code"] == 4
    assert parsed["threat_flag"] is False


def _http_response(*, status_code: int, body: str) -> MagicMock:
    response = MagicMock()
    response.status = status_code
    response.getcode.return_value = status_code
    response.headers = {}
    response.read.return_value = body.encode("utf-8")
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_fetch_site_status_retries_and_sets_user_agent():
    success_response = _http_response(
        status_code=200,
        body=(
            ")]}'\n\n"
            '[["sb.ssr",4,false,false,false,false,false,1767633340523,"google.com"]]\n'
        ),
    )

    with patch("safe_browsing_status_cli.urllib.request.urlopen") as urlopen:
        urlopen.side_effect = [
            urllib.error.URLError("temporary"),
            success_response,
        ]
        with patch("safe_browsing_status_cli.time.sleep") as sleep:
            parsed = cli.fetch_site_status("google.com", retries=2)

    assert parsed["site"] == "google.com"
    assert urlopen.call_count == 2
    sleep.assert_called_once()
    request = urlopen.call_args_list[-1].args[0]
    assert request.get_header("User-agent").startswith("AdminPanelAZ-SafeBrowsingMonitor/")
