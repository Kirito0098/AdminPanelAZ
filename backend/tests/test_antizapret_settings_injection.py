"""setup is a KEY=VALUE file read by root scripts: a newline in a value must never be written."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import require_admin
from app.database import get_db
from app.routers import routing
from app.services.antizapret_params import ANTIZAPRET_PARAMS
from app.services.antizapret_settings import (
    normalize_string,
    update_antizapret_settings,
)


def _param(env: str) -> dict:
    return next(p for p in ANTIZAPRET_PARAMS if p["env"] == env)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(routing.router)
    # Validation raises before any DB/adapter work, so plain stubs are enough.
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="admin")
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_normalize_string_rejects_second_line_without_pattern():
    with pytest.raises(ValueError, match="недопустимые символы"):
        normalize_string({"env": "OPENVPN_HOST"}, "vpn.example.com\nRM -rf /")


@pytest.mark.parametrize("value", ["vpn.example.com\rX=1", "vpn.example.com\tX=1", "vpn example.com"])
def test_normalize_string_rejects_control_chars(value: str):
    with pytest.raises(ValueError, match="недопустимые символы"):
        normalize_string({"env": "OPENVPN_HOST"}, value)


def test_normalize_string_keeps_plain_value():
    assert normalize_string({"env": "OPENVPN_HOST"}, "vpn.example.com") == "vpn.example.com"


def test_normalize_string_still_honours_pattern():
    param = {"env": "X", "pattern": r"[a-z]+"}
    assert normalize_string(param, "abc") == "abc"
    with pytest.raises(ValueError):
        normalize_string(param, "ABC")


@pytest.mark.parametrize("value", ["vpn.example.com", "10.0.0.7", "[2001:db8::7]"])
def test_host_params_accept_domain_and_ip(value: str):
    assert normalize_string(_param("OPENVPN_HOST"), value) == value
    assert normalize_string(_param("WIREGUARD_HOST"), value) == value


@pytest.mark.parametrize(
    "value",
    [
        "https://vpn.example.com",
        "vpn.example.com:1194",
        "vpn.example.com/path",
        "2001:db8::7",
        "vpn.example.com\nRM -rf /",
    ],
)
def test_host_params_reject_scheme_port_path_and_injection(value: str):
    with pytest.raises(ValueError):
        normalize_string(_param("OPENVPN_HOST"), value)


def test_host_params_allow_empty_to_keep_default():
    assert normalize_string(_param("OPENVPN_HOST"), "") == ""


def test_warp_endpoint_pattern_unchanged():
    param = _param("WARP_ENDPOINT")
    assert normalize_string(param, "162.159.192.1:500") == "162.159.192.1:500"
    with pytest.raises(ValueError):
        normalize_string(param, "162.159.192.1:70000")


def test_update_settings_rejects_newline_and_creates_no_file(tmp_path):
    setup = tmp_path / "setup"
    with pytest.raises(ValueError):
        update_antizapret_settings(setup, {"openvpn_host": "a\nb"})
    assert not setup.exists()


def test_update_settings_rejects_newline_without_touching_file(tmp_path):
    setup = tmp_path / "setup"
    original = "OPENVPN_HOST=vpn.example.com\nWIREGUARD_HOST=vpn.example.com\n"
    setup.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError):
        update_antizapret_settings(setup, {"openvpn_host": "vpn.example.com\nevil=1"})

    assert setup.read_text(encoding="utf-8") == original


def test_update_settings_writes_valid_host(tmp_path):
    setup = tmp_path / "setup"
    update_antizapret_settings(setup, {"openvpn_host": "vpn.example.com"})
    assert "OPENVPN_HOST=vpn.example.com\n" in setup.read_text(encoding="utf-8")


def test_put_settings_rejects_newline_value(client: TestClient):
    resp = client.put("/routing/antizapret-settings", json={"openvpn_host": "a\nb"})
    assert resp.status_code == 400
    assert "openvpn_host" in resp.json()["detail"]


def test_put_settings_rejects_overlong_value(client: TestClient):
    resp = client.put("/routing/antizapret-settings", json={"openvpn_host": "a" * 513})
    assert resp.status_code == 400


def test_put_settings_rejects_non_string_value(client: TestClient):
    resp = client.put("/routing/antizapret-settings", json={"openvpn_host": 1})
    assert resp.status_code == 422
