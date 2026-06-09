"""Per-node mTLS scheme selection in RemoteNodeAdapter."""

import subprocess
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.services.node_adapter import RemoteNodeAdapter
from app.services.node_mtls import build_node_agent_ssl_context, node_agent_base_scheme


def _write_mtls_materials(mtls_dir):
    mtls_dir.mkdir(parents=True, exist_ok=True)
    ca_key = mtls_dir / "ca.key"
    ca_crt = mtls_dir / "ca.crt"
    panel_key = mtls_dir / "panel.key"
    panel_crt = mtls_dir / "panel.crt"

    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(ca_key), "-out", str(ca_crt), "-days", "1",
         "-subj", "/CN=test-ca"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["openssl", "req", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(panel_key), "-out", str(mtls_dir / "panel.csr"),
         "-subj", "/CN=test-panel"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["openssl", "x509", "-req", "-in", str(mtls_dir / "panel.csr"),
         "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
         "-out", str(panel_crt), "-days", "1"],
        check=True,
        capture_output=True,
    )
    return ca_crt, panel_crt, panel_key


def test_node_agent_base_scheme_per_node():
    assert node_agent_base_scheme(mtls_enabled=False) == "http"
    assert node_agent_base_scheme(mtls_enabled=True) == "https"


def test_remote_adapter_http_when_mtls_disabled():
    adapter = RemoteNodeAdapter("10.0.0.1", 9100, "k" * 32, mtls_enabled=False)
    assert adapter.base_url == "http://10.0.0.1:9100"
    assert adapter._verify is None
    assert adapter._mtls_enabled is False


def test_remote_adapter_https_when_mtls_enabled(tmp_path, monkeypatch):
    mtls_dir = tmp_path / "mtls"
    ca_crt, panel_crt, panel_key = _write_mtls_materials(mtls_dir)

    monkeypatch.setattr(
        "app.services.node_mtls.get_settings",
        lambda: Settings(
            node_agent_mtls_ca_cert=str(ca_crt),
            node_agent_mtls_client_cert=str(panel_crt),
            node_agent_mtls_client_key=str(panel_key),
        ),
    )

    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=True)
    assert adapter.base_url == "https://10.0.0.2:9100"
    assert adapter._verify is not None
    assert adapter._mtls_enabled is True


def test_remote_adapter_global_mtls_fallback(monkeypatch):
    monkeypatch.setattr(
        "app.services.node_mtls.get_settings",
        lambda: Settings(node_agent_mtls_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.node_adapter.node_agent_mtls_enabled",
        lambda: True,
    )

    adapter = RemoteNodeAdapter("10.0.0.3", 9100, "k" * 32)
    assert adapter.base_url == "https://10.0.0.3:9100"
    assert adapter._mtls_enabled is True


def test_build_node_agent_ssl_context_skips_when_disabled():
    assert build_node_agent_ssl_context(mtls_enabled=False) is None


def test_wrong_version_number_https_panel_http_node():
    adapter = RemoteNodeAdapter("10.0.0.1", 9100, "k" * 32, mtls_enabled=True)
    exc = httpx.ConnectError(
        "[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1000)",
        request=httpx.Request("GET", "https://10.0.0.1:9100/health"),
    )
    msg = adapter._format_connection_error(exc)
    assert "WRONG_VERSION_NUMBER" in msg
    assert "HTTP" in msg
    assert "HTTPS" in msg


def test_wrong_version_number_http_panel_https_node():
    adapter = RemoteNodeAdapter("10.0.0.1", 9100, "k" * 32, mtls_enabled=False)
    exc = httpx.ConnectError(
        "wrong version number",
        request=httpx.Request("GET", "http://10.0.0.1:9100/health"),
    )
    msg = adapter._format_connection_error(exc)
    assert "WRONG_VERSION_NUMBER" in msg
    assert "HTTPS" in msg
    assert "HTTP" in msg


def test_mixed_nodes_use_different_schemes(tmp_path, monkeypatch):
    mtls_dir = tmp_path / "mtls"
    ca_crt, panel_crt, panel_key = _write_mtls_materials(mtls_dir)

    monkeypatch.setattr(
        "app.services.node_mtls.get_settings",
        lambda: Settings(
            node_agent_mtls_ca_cert=str(ca_crt),
            node_agent_mtls_client_cert=str(panel_crt),
            node_agent_mtls_client_key=str(panel_key),
        ),
    )

    http_node = RemoteNodeAdapter("10.0.0.10", 9100, "k" * 32, mtls_enabled=False)
    https_node = RemoteNodeAdapter("10.0.0.20", 9100, "k" * 32, mtls_enabled=True)

    assert http_node.base_url.startswith("http://")
    assert https_node.base_url.startswith("https://")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"status":"ok"}'
    mock_response.json.return_value = {"status": "ok"}

    with patch("httpx.Client") as client_cls:
        mock_client = MagicMock()
        mock_client.request.return_value = mock_response
        client_cls.return_value = mock_client

        http_node.health_check()
        https_node.health_check()

        http_url = mock_client.request.call_args_list[0].args[1]
        https_url = mock_client.request.call_args_list[1].args[1]
        assert http_url == "http://10.0.0.10:9100/health"
        assert https_url == "https://10.0.0.20:9100/health"


def test_request_raises_503_with_scheme_mismatch_hint(tmp_path, monkeypatch):
    adapter = RemoteNodeAdapter("10.0.0.1", 9100, "k" * 32, mtls_enabled=False)
    exc = httpx.ConnectError(
        "wrong version number",
        request=httpx.Request("GET", "http://10.0.0.1:9100/health"),
    )

    with patch.object(adapter, "_get_http_client") as get_client:
        mock_client = MagicMock()
        mock_client.request.side_effect = exc
        get_client.return_value = mock_client

        with pytest.raises(HTTPException) as err:
            adapter.health_check()

    assert err.value.status_code == 503
    assert "WRONG_VERSION_NUMBER" in str(err.value.detail)


@pytest.mark.parametrize(
    ("error_text", "mtls_enabled", "expected_fragment"),
    [
        (
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
            True,
            "проверки сертификата",
        ),
        (
            "sslv3 alert certificate expired",
            True,
            "истёк",
        ),
        (
            "self signed certificate in certificate chain",
            True,
            "самоподписанный",
        ),
        (
            "tlsv1 alert unknown ca",
            True,
            "unknown CA",
        ),
        (
            "sslv3 alert handshake failure",
            True,
            "TLS handshake",
        ),
        (
            "some generic ssl error",
            False,
            "HTTPS (mTLS)",
        ),
    ],
)
def test_ssl_error_messages(error_text, mtls_enabled, expected_fragment):
    adapter = RemoteNodeAdapter("10.0.0.1", 9100, "k" * 32, mtls_enabled=mtls_enabled)
    exc = httpx.ConnectError(
        error_text,
        request=httpx.Request("GET", f"{'https' if mtls_enabled else 'http'}://10.0.0.1:9100/health"),
    )
    msg = adapter._format_connection_error(exc)
    assert expected_fragment in msg
