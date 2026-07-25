"""Unit tests for DDNS settings helpers (parse/write/mask, no systemd)."""

from pathlib import Path

import pytest

from app.services.ddns_settings import (
    DdnsConfig,
    build_ddns_env_text,
    clear_ddns_config,
    load_ddns_config,
    merge_secret_fields,
    parse_ddns_env_text,
    public_ddns_status,
    resolve_ddns_domain,
    write_ddns_config,
)


def test_parse_ddns_env_text_quoted():
    text = """
# comment
DDNS_PROVIDER='duckdns'
DDNS_DOMAIN='myvpn.duckdns.org'
DDNS_SUBDOMAIN='myvpn'
DDNS_TOKEN='secret-token'
DDNS_PASSWORD='pass with spaces'
"""
    data = parse_ddns_env_text(text)
    assert data["DDNS_PROVIDER"] == "duckdns"
    assert data["DDNS_DOMAIN"] == "myvpn.duckdns.org"
    assert data["DDNS_SUBDOMAIN"] == "myvpn"
    assert data["DDNS_TOKEN"] == "secret-token"
    assert data["DDNS_PASSWORD"] == "pass with spaces"


def test_resolve_ddns_domain():
    assert resolve_ddns_domain("duckdns", subdomain="MyVPN") == "myvpn.duckdns.org"
    assert resolve_ddns_domain("duckdns", subdomain="myvpn.duckdns.org") == "myvpn.duckdns.org"
    assert resolve_ddns_domain("noip", hostname="home.ddns.net") == "home.ddns.net"
    assert resolve_ddns_domain("none") == ""


def test_build_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "ddns.env"
    cfg = write_ddns_config(
        "duckdns",
        subdomain="lab",
        token="secret-token",
        path=path,
    )
    assert cfg.provider == "duckdns"
    assert cfg.domain == "lab.duckdns.org"
    assert cfg.token == "secret-token"
    assert path.read_text(encoding="utf-8").count("secret-token") == 1

    loaded = load_ddns_config(path)
    assert loaded == cfg


def test_build_noip(tmp_path: Path):
    path = tmp_path / "ddns.env"
    cfg = write_ddns_config(
        "noip",
        hostname="x.ddns.net",
        username="user",
        password="pass with spaces",
        path=path,
    )
    assert cfg.provider == "noip"
    assert cfg.hostname == "x.ddns.net"
    assert cfg.password == "pass with spaces"
    reloaded = load_ddns_config(path)
    assert reloaded.password == "pass with spaces"


def test_build_rejects_incomplete():
    with pytest.raises(ValueError, match="DuckDNS"):
        build_ddns_env_text("duckdns", subdomain="a", token="")
    with pytest.raises(ValueError, match="No-IP"):
        build_ddns_env_text("noip", hostname="h", username="u", password="")


def test_clear_ddns_config(tmp_path: Path):
    path = tmp_path / "ddns.env"
    write_ddns_config("duckdns", subdomain="a", token="t", path=path)
    assert path.is_file()
    clear_ddns_config(path)
    assert not path.exists()
    assert load_ddns_config(path).provider == "none"


def test_merge_secret_fields_keeps_existing():
    existing = DdnsConfig(provider="duckdns", subdomain="a", token="kept-token")
    token, _ = merge_secret_fields("duckdns", existing, token="****")
    assert token == "kept-token"
    token2, _ = merge_secret_fields("duckdns", existing, token="")
    assert token2 == "kept-token"
    token3, _ = merge_secret_fields("duckdns", existing, token="new-token")
    assert token3 == "new-token"

    existing_noip = DdnsConfig(provider="noip", hostname="h", password="kept-pass")
    _, password = merge_secret_fields("noip", existing_noip, password="****")
    assert password == "kept-pass"


def test_public_ddns_status_masks_secrets(tmp_path: Path, monkeypatch):
    path = tmp_path / "ddns.env"
    write_ddns_config("duckdns", subdomain="lab", token="super-secret", path=path)
    monkeypatch.setenv("DDNS_CONFIG", str(path))

    def fake_timer():
        return {"timer_enabled": True, "timer_active": True, "timer_detail": "активен"}

    monkeypatch.setattr("app.services.ddns_settings.timer_status", fake_timer)
    status = public_ddns_status()
    assert status["provider"] == "duckdns"
    assert status["domain"] == "lab.duckdns.org"
    assert status["token_configured"] is True
    assert status["token_masked"] == "****"
    assert "super-secret" not in str(status.values())
    assert status["timer_enabled"] is True
