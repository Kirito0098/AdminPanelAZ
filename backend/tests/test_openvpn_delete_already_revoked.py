"""Deleting an OpenVPN client whose certificate is already revoked cleans leftover files."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.antizapret import AntiZapretService
from app.services.openvpn_pki import EasyRsaIndexEntry, ProfileCertIssue, ProfileValidationResult

REVOKE_CONFLICT_DETAIL = (
    "Ошибка AntiZapret: OpenVPN - Delete client mira\n\nUsing SSL:\n* openssl OpenSSL 3.0.13\n\n"
    "Error\n-----\nCannot revoke this certificate, a conflicting file exists."
)

NO_CERTIFICATE_DETAIL = (
    "Ошибка AntiZapret: OpenVPN - Delete client android_test\n\n"
    "No Easy-RSA vars configuration file exists!\nEasyRSA version 3.1.7\n"
    "Error\n-----\n"
    "Unable to revoke as no certificate was found. Certificate was expected at:\n"
    "/etc/openvpn/easyrsa3/pki/issued/android_test.crt"
)


def _service(tmp_path: Path) -> AntiZapretService:
    service = AntiZapretService(base_path=tmp_path)
    service.openvpn_ccd_dir = tmp_path / "ccd"
    service.openvpn_ccd_dir.mkdir()
    return service


def _profile(tmp_path: Path, name: str = "mira") -> Path:
    directory = tmp_path / "client" / "openvpn" / "antizapret"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"antizapret-{name}-(1.2.3.4).ovpn"
    path.write_text("client\n", encoding="utf-8")
    return path


def _fail_script(monkeypatch, service: AntiZapretService, detail: str) -> None:
    def raiser(*_args, **_kwargs):
        raise HTTPException(status_code=500, detail=detail)

    monkeypatch.setattr(service, "_run_client_script", raiser)


def _pki_state(monkeypatch, *, issues: tuple[ProfileCertIssue, ...]) -> None:
    result = ProfileValidationResult(ready=not issues, issues=issues)
    monkeypatch.setattr("app.services.openvpn_pki.validate_client_profiles", lambda *_a, **_k: result)


def _issue(status: str) -> ProfileCertIssue:
    return ProfileCertIssue(
        client_name="mira",
        path="/root/antizapret/client/openvpn/antizapret/antizapret-mira-(1.2.3.4).ovpn",
        filename="antizapret-mira-(1.2.3.4).ovpn",
        serial_hex="C63509A369F02E6511D6B77514B44470",
        status=status,
    )


def test_delete_falls_back_to_cleanup_when_the_certificate_is_already_revoked(tmp_path, monkeypatch):
    service = _service(tmp_path)
    profile = _profile(tmp_path)
    ccd = service.openvpn_ccd_dir / "mira"
    ccd.write_text("", encoding="utf-8")
    _fail_script(monkeypatch, service, REVOKE_CONFLICT_DETAIL)
    _pki_state(monkeypatch, issues=(_issue("revoked"),))

    message = service.delete_openvpn_client("mira")

    assert "уже отозван" in message
    assert not profile.exists()
    assert not ccd.exists()


def test_delete_keeps_the_error_when_the_certificate_is_still_valid(tmp_path, monkeypatch):
    service = _service(tmp_path)
    profile = _profile(tmp_path)
    _fail_script(monkeypatch, service, REVOKE_CONFLICT_DETAIL)
    _pki_state(monkeypatch, issues=())

    with pytest.raises(HTTPException) as excinfo:
        service.delete_openvpn_client("mira")

    assert excinfo.value.status_code == 500
    assert profile.exists()


def test_delete_keeps_the_error_for_unrelated_failures(tmp_path, monkeypatch):
    service = _service(tmp_path)
    profile = _profile(tmp_path)
    _fail_script(monkeypatch, service, "Ошибка AntiZapret: timeout while talking to openvpn")
    _pki_state(monkeypatch, issues=(_issue("revoked"),))

    with pytest.raises(HTTPException):
        service.delete_openvpn_client("mira")

    assert profile.exists()


def test_delete_reports_success_when_the_script_succeeds(tmp_path, monkeypatch):
    service = _service(tmp_path)
    profile = _profile(tmp_path)
    monkeypatch.setattr(service, "_run_client_script", lambda *_a, **_k: "client mira deleted")

    assert service.delete_openvpn_client("mira") == "client mira deleted"
    assert profile.exists()


def test_delete_succeeds_when_the_certificate_and_profiles_are_gone(tmp_path, monkeypatch):
    """EasyRSA «no certificate was found» + no profiles/valid cert = client already gone."""
    service = _service(tmp_path)
    ccd = service.openvpn_ccd_dir / "android_test"
    ccd.write_text("", encoding="utf-8")
    _fail_script(monkeypatch, service, NO_CERTIFICATE_DETAIL)
    monkeypatch.setattr(service, "get_profile_files", lambda *_a, **_k: [])
    monkeypatch.setattr("app.services.openvpn_pki.load_easyrsa_index", lambda *_a, **_k: [])

    message = service.delete_openvpn_client("android_test")

    assert "отсутств" in message
    assert not ccd.exists()


def test_delete_keeps_the_error_when_the_ca_still_holds_a_valid_certificate(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _fail_script(monkeypatch, service, NO_CERTIFICATE_DETAIL)
    monkeypatch.setattr(service, "get_profile_files", lambda *_a, **_k: [])
    monkeypatch.setattr(
        "app.services.openvpn_pki.load_easyrsa_index",
        lambda *_a, **_k: [
            EasyRsaIndexEntry(
                status="V",
                expiry="2036-01-01 00:00:00",
                serial_hex="C63509A369F02E6511D6B77514B44470",
                common_name="android_test",
            )
        ],
    )

    with pytest.raises(HTTPException) as excinfo:
        service.delete_openvpn_client("android_test")

    assert excinfo.value.status_code == 500


def test_delete_keeps_the_error_when_profiles_still_exist(tmp_path, monkeypatch):
    service = _service(tmp_path)
    profile = _profile(tmp_path, "android_test")
    _fail_script(monkeypatch, service, NO_CERTIFICATE_DETAIL)
    monkeypatch.setattr("app.services.openvpn_pki.load_easyrsa_index", lambda *_a, **_k: [])

    with pytest.raises(HTTPException):
        service.delete_openvpn_client("android_test")

    assert profile.exists()

