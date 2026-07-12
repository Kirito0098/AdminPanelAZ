"""Tests for EasyRSA index parsing and OpenVPN profile cert validation."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models import VpnType
from app.services.openvpn_pki import (
    cert_serial_hex_from_pem,
    find_valid_serials,
    is_serial_revoked,
    parse_easyrsa_index,
    profile_issues_payload,
    validate_client_profiles,
)

SAMPLE_INDEX = """\
R\t360406211315Z\t260615203626Z\tF401806F35A8048BA0941A9F085EF9C2\tunknown\t/CN=AN_Claymore
V\t360405210223Z\tC9014ACA2099B8A6FB3F856105979E79\tunknown\t/CN=AN_Claymore
V\t350828115322Z\t197E3E2863B7E339EDD7282A8C94A8F8\tunknown\t/CN=AN_Claymore
"""


def test_parse_easyrsa_index_revoked_and_valid_entries():
    entries = parse_easyrsa_index(SAMPLE_INDEX)
    assert len(entries) == 3
    revoked = [entry for entry in entries if entry.common_name == "AN_Claymore" and entry.status == "R"]
    valid = [entry for entry in entries if entry.common_name == "AN_Claymore" and entry.status == "V"]
    assert len(revoked) == 1
    assert revoked[0].serial_hex == "F401806F35A8048BA0941A9F085EF9C2"
    assert len(valid) == 2


def test_is_serial_revoked_matches_index():
    entries = parse_easyrsa_index(SAMPLE_INDEX)
    assert is_serial_revoked("F401806F35A8048BA0941A9F085EF9C2", entries)
    assert not is_serial_revoked("C9014ACA2099B8A6FB3F856105979E79", entries)


def test_find_valid_serials_for_cn():
    entries = parse_easyrsa_index(SAMPLE_INDEX)
    serials = find_valid_serials("AN_Claymore", entries)
    assert "C9014ACA2099B8A6FB3F856105979E79" in serials
    assert "F401806F35A8048BA0941A9F085EF9C2" not in serials


def test_cert_serial_hex_from_pem_normalizes_decimal_output(monkeypatch):
    class Result:
        returncode = 0
        stdout = "serial=324339428227739140836673998017213168066\n"

    monkeypatch.setattr("app.services.openvpn_pki.subprocess.run", lambda *args, **kwargs: Result())
    assert cert_serial_hex_from_pem("dummy-pem") == "F401806F35A8048BA0941A9F085EF9C2"


def test_validate_client_profiles_flags_revoked_cert_in_ovpn(monkeypatch):
    adapter = MagicMock()
    adapter.read_easyrsa_index.return_value = SAMPLE_INDEX
    adapter.get_profile_files.return_value = [
        {
            "path": "/root/antizapret/client/openvpn/antizapret-udp/antizapret-udp-AN_Claymore-udp.ovpn",
            "filename": "antizapret-udp-AN_Claymore-udp.ovpn",
        }
    ]
    adapter.read_profile_file.return_value = (
        "<cert>\n"
        "-----BEGIN CERTIFICATE-----\n"
        "MIIB\n"
        "-----END CERTIFICATE-----\n"
        "</cert>"
    )

    def fake_serial(pem: str) -> str | None:
        return "F401806F35A8048BA0941A9F085EF9C2"

    monkeypatch.setattr("app.services.openvpn_pki.cert_serial_hex_from_pem", fake_serial)
    monkeypatch.setattr(
        "app.services.openvpn_pki.cert_not_after_utc",
        lambda pem: datetime(2036, 4, 6, tzinfo=timezone.utc),
    )
    result = validate_client_profiles(adapter, "AN_Claymore")

    assert not result.ready
    assert len(result.issues) == 1
    assert result.issues[0].status == "revoked"
    payload = profile_issues_payload(result)
    assert payload[0]["client_name"] == "AN_Claymore"
    adapter.get_profile_files.assert_called_once_with("AN_Claymore", VpnType.openvpn)
