"""Deleting a client that is already gone must finish, not fail the whole cleanup."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.antizapret import AntiZapretService

WG_MISSING_DETAIL = (
    "Ошибка AntiZapret: WireGuard/AmneziaWG - Delete client android_test\n\n"
    "Failed to delete client 'android_test'! Please check if client exists"
)


def _service(tmp_path: Path) -> AntiZapretService:
    service = AntiZapretService(base_path=tmp_path)
    service.openvpn_ccd_dir = tmp_path / "ccd"
    service.openvpn_ccd_dir.mkdir()
    return service


def _fail_script(monkeypatch, service: AntiZapretService, detail: str) -> None:
    def raiser(*_args, **_kwargs):
        raise HTTPException(status_code=500, detail=detail)

    monkeypatch.setattr(service, "_run_client_script", raiser)


def _wireguard_profile(tmp_path: Path, name: str = "android_test") -> Path:
    directory = tmp_path / "client" / "wireguard" / "antizapret"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"antizapret-{name}-wg.conf"
    path.write_text("[Interface]\n", encoding="utf-8")
    return path


def test_wireguard_delete_succeeds_when_the_client_is_already_gone(tmp_path, monkeypatch):
    service = _service(tmp_path)
    profile = _wireguard_profile(tmp_path)
    _fail_script(monkeypatch, service, WG_MISSING_DETAIL)
    monkeypatch.setattr(service, "list_wireguard_clients", lambda: ["someone_else"])

    message = service.delete_wireguard_client("android_test")

    assert "отсутств" in message
    assert not profile.exists()


def test_wireguard_delete_keeps_the_error_when_the_client_still_exists(tmp_path, monkeypatch):
    service = _service(tmp_path)
    profile = _wireguard_profile(tmp_path)
    _fail_script(monkeypatch, service, WG_MISSING_DETAIL)
    monkeypatch.setattr(service, "list_wireguard_clients", lambda: ["android_test"])

    with pytest.raises(HTTPException):
        service.delete_wireguard_client("android_test")

    assert profile.exists()


def test_wireguard_delete_keeps_unrelated_errors(tmp_path, monkeypatch):
    service = _service(tmp_path)
    profile = _wireguard_profile(tmp_path)
    _fail_script(monkeypatch, service, "Ошибка AntiZapret: timeout while talking to wg")
    monkeypatch.setattr(service, "list_wireguard_clients", lambda: [])

    with pytest.raises(HTTPException):
        service.delete_wireguard_client("android_test")

    assert profile.exists()
