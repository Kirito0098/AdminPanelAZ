"""Tests for panel publish info (VPN network tab)."""

from app.services.panel_publish_info import (
    build_panel_publish_context,
    is_whitelist_port_firewall_applicable,
    resolve_panel_publish_mode,
)


def _settings_stub(**overrides):
    from app.config import Settings

    base = Settings(
        app_env="development",
        behind_nginx=False,
        domain="",
        enforce_https=False,
        trusted_proxy_ips="127.0.0.1,::1",
        forwarded_allow_ips="127.0.0.1,::1",
        refresh_token_cookie_secure=False,
    )
    return base.model_copy(update=overrides)


def test_reverse_proxy_with_domain():
    env = {
        "BACKEND_HOST": "127.0.0.1",
        "BACKEND_PORT": "8000",
        "BEHIND_NGINX": "true",
        "DOMAIN": "panel.example.com",
        "REFRESH_TOKEN_COOKIE_SECURE": "true",
        "TRUSTED_PROXY_IPS": "127.0.0.1,::1",
        "FORWARDED_ALLOW_IPS": "127.0.0.1,::1",
        "ENFORCE_HTTPS": "false",
    }

    def get_env_value(key, default=""):
        return env.get(key, default)

    ctx = build_panel_publish_context(
        get_env_value=get_env_value,
        request_url="https://panel.example.com/settings",
        settings=_settings_stub(behind_nginx=True, domain="panel.example.com"),
    )
    assert ctx["mode_key"] == "reverse_proxy"
    assert len(ctx["primary_urls"]) == 1
    assert ctx["primary_urls"][0]["url"] == "https://panel.example.com/"


def test_reverse_proxy_dedup_primary_urls():
    env = {
        "BACKEND_HOST": "127.0.0.1",
        "BACKEND_PORT": "8000",
        "BEHIND_NGINX": "true",
        "DOMAIN": "panel.example.com",
    }

    def get_env_value(key, default=""):
        return env.get(key, default)

    ctx = build_panel_publish_context(
        get_env_value=get_env_value,
        request_url="https://panel.example.com/",
        settings=_settings_stub(behind_nginx=True, domain="panel.example.com"),
    )
    urls = [row["url"] for row in ctx["primary_urls"]]
    assert urls.count("https://panel.example.com/") == 1


def test_direct_http():
    env = {
        "BACKEND_HOST": "0.0.0.0",
        "BACKEND_PORT": "8000",
        "BEHIND_NGINX": "false",
        "DOMAIN": "",
        "REFRESH_TOKEN_COOKIE_SECURE": "false",
        "TRUSTED_PROXY_IPS": "",
        "FORWARDED_ALLOW_IPS": "",
        "ENFORCE_HTTPS": "false",
    }

    def get_env_value(key, default=""):
        return env.get(key, default)

    ctx = build_panel_publish_context(
        get_env_value=get_env_value,
        request_url="http://192.0.2.1:8000/",
        settings=_settings_stub(),
    )
    assert ctx["mode_key"] == "direct_http"
    assert ctx["internal_url"] == "http://0.0.0.0:8000/"


def test_local_http():
    env = {
        "BACKEND_HOST": "127.0.0.1",
        "BACKEND_PORT": "8000",
        "BEHIND_NGINX": "false",
        "DOMAIN": "",
    }

    def get_env_value(key, default=""):
        return env.get(key, default)

    ctx = build_panel_publish_context(
        get_env_value=get_env_value,
        request_url="http://127.0.0.1:8000/",
        settings=_settings_stub(),
    )
    assert ctx["mode_key"] == "local_http"
    assert ctx["internal_url"] == "http://127.0.0.1:8000/"


def test_whitelist_firewall_applicable_direct_http():
    assert is_whitelist_port_firewall_applicable(
        get_env_value=lambda k, d="": {
            "BACKEND_HOST": "0.0.0.0",
            "BEHIND_NGINX": "false",
        }.get(k, d)
    )


def test_whitelist_firewall_not_applicable_behind_nginx():
    assert not is_whitelist_port_firewall_applicable(
        get_env_value=lambda k, d="": {
            "BACKEND_HOST": "127.0.0.1",
            "BEHIND_NGINX": "true",
        }.get(k, d)
    )


def test_whitelist_firewall_not_applicable_local_http():
    assert not is_whitelist_port_firewall_applicable(
        get_env_value=lambda k, d="": {
            "BACKEND_HOST": "127.0.0.1",
            "BEHIND_NGINX": "false",
        }.get(k, d)
    )


def test_resolve_panel_publish_mode():
    assert resolve_panel_publish_mode(behind_nginx=True, backend_host="127.0.0.1") == "reverse_proxy"
    assert resolve_panel_publish_mode(behind_nginx=False, backend_host="0.0.0.0") == "direct_http"
    assert resolve_panel_publish_mode(behind_nginx=False, backend_host="127.0.0.1") == "local_http"
