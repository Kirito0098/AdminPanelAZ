from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import Settings
from app.middleware.http_security import get_panel_branding
from app.services.panel_publish_info import (
    build_panel_publish_context,
    build_publish_access_url,
    infer_nginx_publish_mode_from_cert,
    is_whitelist_port_firewall_applicable,
    nginx_listens_on_https_port,
    public_https_origin_host,
    public_https_origin_url,
    resolve_active_publish_mode_key,
)


def test_public_https_origin_host_standard_port():
    assert public_https_origin_host("example.com", 443) == "example.com"
    assert public_https_origin_url("example.com", 443) == "https://example.com"


def test_public_https_origin_host_custom_port():
    assert public_https_origin_host("example.com", 5050) == "example.com:5050"
    assert public_https_origin_url("example.com", 5050) == "https://example.com:5050"


def test_build_publish_access_url_uvicorn_includes_nonstandard_port():
    url = build_publish_access_url(
        publish_mode="uvicorn_le",
        domain="example.com",
        backend_port=5050,
    )
    assert url == "https://example.com:5050/"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"BEHIND_NGINX": "false", "BACKEND_HOST": "0.0.0.0", "USE_HTTPS": "false"}, True),
        ({"BEHIND_NGINX": "false", "BACKEND_HOST": "0.0.0.0", "USE_HTTPS": "true"}, True),
        ({"BEHIND_NGINX": "true", "BACKEND_HOST": "127.0.0.1", "USE_HTTPS": "false"}, False),
        ({"BEHIND_NGINX": "false", "BACKEND_HOST": "127.0.0.1", "USE_HTTPS": "false"}, False),
        ({"BEHIND_NGINX": "false", "BACKEND_HOST": "127.0.0.1", "USE_HTTPS": "true"}, False),
    ],
)
def test_is_whitelist_port_firewall_applicable(env, expected):
    assert (
        is_whitelist_port_firewall_applicable(get_env_value=lambda key, default="": env.get(key, default))
        is expected
    )


def test_public_https_origin_host_strips_domain_port_suffix():
    assert public_https_origin_host("example.com:8443", 443) == "example.com"
    assert public_https_origin_host("example.com:8443", 5050) == "example.com:5050"


def test_get_panel_branding_uses_https_public_port():
    branding = get_panel_branding(
        {
            "DOMAIN": "panel.example.com",
            "HTTPS_PUBLIC_PORT": "5050",
        }
    )
    assert branding["panel_base_url"] == "https://panel.example.com:5050"


def test_resolve_active_publish_mode_explicit_publish_mode():
    assert (
        resolve_active_publish_mode_key(
            mode_key="reverse_proxy",
            ssl_cert="",
            publish_mode="nginx_selfsigned",
            domain="example.com",
        )
        == "nginx_selfsigned"
    )


def test_resolve_active_publish_mode_nginx_selfsigned_from_cert():
    cert = "/etc/ssl/certs/adminpanelaz.crt"
    assert (
        resolve_active_publish_mode_key(
            mode_key="reverse_proxy",
            ssl_cert=cert,
            publish_mode="",
            domain="example.com",
        )
        == "nginx_selfsigned"
    )


def test_resolve_active_publish_mode_nginx_custom_from_cert():
    cert = "/etc/ssl/private/my-panel/fullchain.pem"
    assert (
        resolve_active_publish_mode_key(
            mode_key="reverse_proxy",
            ssl_cert=cert,
            publish_mode="",
            domain="example.com",
        )
        == "nginx_custom"
    )


def test_resolve_active_publish_mode_nginx_le_from_letsencrypt_cert():
    cert = "/etc/letsencrypt/live/example.com/fullchain.pem"
    assert (
        resolve_active_publish_mode_key(
            mode_key="reverse_proxy",
            ssl_cert=cert,
            publish_mode="",
            domain="example.com",
        )
        == "nginx_le"
    )


def test_resolve_active_publish_mode_nginx_from_vhost_cert(monkeypatch, tmp_path: Path):
    vhost = tmp_path / "example_com"
    vhost.write_text(
        "# AdminPanelAZ — panel\n"
        "server_name example.com;\n"
        "ssl_certificate /etc/ssl/certs/adminpanelaz.crt;\n",
        encoding="utf-8",
    )

    def fake_iter(domain: str):
        assert domain == "example.com"
        return [vhost]

    def fake_is_ours(path: Path) -> bool:
        return path == vhost

    monkeypatch.setattr(
        "app.services.panel_publish_info._nginx_iter_vhost_files_for_domain",
        fake_iter,
    )
    monkeypatch.setattr(
        "app.services.panel_publish_info._nginx_is_our_panel_vhost_file",
        fake_is_ours,
    )
    monkeypatch.setattr(
        "app.services.panel_publish_info.letsencrypt_exists_for_domain",
        lambda _domain: False,
    )
    monkeypatch.setattr(
        "app.services.panel_publish_info.SELF_SIGNED_CERT_PATH",
        Path("/missing/adminpanelaz.crt"),
    )

    assert (
        resolve_active_publish_mode_key(
            mode_key="reverse_proxy",
            ssl_cert="",
            publish_mode="",
            domain="example.com",
        )
        == "nginx_selfsigned"
    )


def test_infer_nginx_publish_mode_from_cert():
    assert infer_nginx_publish_mode_from_cert("/etc/letsencrypt/live/x/fullchain.pem") == "nginx_le"
    assert infer_nginx_publish_mode_from_cert("/etc/ssl/certs/adminpanelaz.crt") == "nginx_selfsigned"
    assert infer_nginx_publish_mode_from_cert("/custom/cert.pem") == "nginx_custom"
    assert infer_nginx_publish_mode_from_cert("") == "nginx_le"


def test_build_panel_publish_context_includes_http_acme_port():
    settings = Settings()
    ctx = build_panel_publish_context(
        get_env_value=lambda key, default="": {
            "BEHIND_NGINX": "true",
            "DOMAIN": "example.com",
            "HTTPS_PUBLIC_PORT": "5050",
            "HTTP_ACME_PORT": "8080",
        }.get(key, default),
        request_url="https://example.com:5050/",
        settings=settings,
    )
    env_map = {row["label"]: row["value"] for row in ctx["env_rows"]}
    assert env_map["HTTPS_PUBLIC_PORT"] == "5050"
    assert env_map["HTTP_ACME_PORT"] == "8080"
    labels = " ".join(entry["label"] for entry in ctx["primary_urls"])
    bullets = " ".join(ctx["bullet_points"])
    assert "HTTP 8080, HTTPS 5050" in labels or "5050" in bullets


@pytest.mark.parametrize(
    ("port", "ss_output", "expected"),
    [
        (443, "LISTEN 0 128 *:443 *:* users:((\"nginx\",pid=1,fd=1))", True),
        (5050, "LISTEN 0 128 *:5050 *:* users:((\"nginx\",pid=1,fd=1))", True),
        (5050, "LISTEN 0 128 *:443 *:* users:((\"nginx\",pid=1,fd=1))", False),
    ],
)
def test_nginx_listens_on_https_port(port, ss_output, expected, monkeypatch):
    monkeypatch.setattr("app.services.panel_publish_info.is_nginx_installed", lambda: True)
    monkeypatch.setattr(
        "app.services.panel_publish_info.subprocess.run",
        lambda *args, **kwargs: type("R", (), {"stdout": ss_output, "returncode": 0})(),
    )
    assert nginx_listens_on_https_port(port) is expected


def test_inspect_tcp_port_no_false_positive_on_substring_port(monkeypatch):
    monkeypatch.setattr(
        "app.services.panel_publish_info.subprocess.run",
        lambda *args, **kwargs: type(
            "R",
            (),
            {
                "stdout": "LISTEN 0 128 *:8080 *:* users:((\"uvicorn\",pid=1,fd=1))",
                "returncode": 0,
            },
        )(),
    )
    from app.services.panel_publish_info import inspect_tcp_port

    result = inspect_tcp_port(80, role="nginx_http")
    assert result["status"] == "free"


def test_build_panel_publish_context_empty_access_path_when_unset_in_env():
    settings = Settings(access_path="/panel")
    defined_keys = {"ACCESS_PATH", "DOMAIN"}

    ctx = build_panel_publish_context(
        get_env_value=lambda key, default="": {
            "BEHIND_NGINX": "true",
            "DOMAIN": "example.com",
        }.get(key, default),
        request_url="https://example.com/",
        settings=settings,
        env_key_defined=lambda key: key in defined_keys,
    )
    access_row = next(row for row in ctx["env_rows"] if row["label"].startswith("ACCESS_PATH"))
    assert access_row["value"] == "—"
    assert ctx["access_path_value"] == ""


def test_build_panel_publish_context_invalid_access_path_does_not_raise():
    settings = Settings(access_path="/panel")
    ctx = build_panel_publish_context(
        get_env_value=lambda key, default="": {
            "BEHIND_NGINX": "true",
            "DOMAIN": "example.com",
            "ACCESS_PATH": "/api",
        }.get(key, default),
        request_url="https://example.com/",
        settings=settings,
    )
    assert ctx["mode_key"] == "reverse_proxy"
    assert any("example.com" in (row.get("url") or "") for row in ctx["primary_urls"])


def test_resolve_active_publish_mode_uvicorn_le_from_disk(monkeypatch):
    monkeypatch.setattr(
        "app.services.panel_publish_info.letsencrypt_exists_for_domain",
        lambda domain: domain == "example.com",
    )
    assert (
        resolve_active_publish_mode_key(
            mode_key="direct_https",
            ssl_cert="",
            publish_mode="",
            domain="example.com",
        )
        == "uvicorn_le"
    )
