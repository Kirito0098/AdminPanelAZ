"""Tests for real certificate expiry: remaining days come from notAfter, not the issued term."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models import VpnType
from app.services.openvpn_cert import (
    days_remaining_until,
    parse_easyrsa_expiry,
    refresh_config_cert_expiry,
    to_naive_utc,
)
from app.services.openvpn_pki import cert_expiry_map_by_cn, parse_easyrsa_index

SAMPLE_INDEX = """\
R\t360406211315Z\t260615203626Z\tF401806F35A8048BA0941A9F085EF9C2\tunknown\t/CN=revoked-client
V\t360405210223Z\t\tC9014ACA2099B8A6FB3F856105979E79\tunknown\t/CN=alice
V\t350828115322Z\t\t197E3E2863B7E339EDD7282A8C94A8F8\tunknown\t/CN=alice
V\t270101000000Z\t\tAABBCCDDEEFF00112233445566778899\tunknown\t/CN=bob
"""


def test_parse_easyrsa_expiry_utctime():
    assert parse_easyrsa_expiry("360405210223Z") == datetime(
        2036, 4, 5, 21, 2, 23, tzinfo=timezone.utc
    )


def test_parse_easyrsa_expiry_generalized_time():
    assert parse_easyrsa_expiry("20360405210223Z") == datetime(
        2036, 4, 5, 21, 2, 23, tzinfo=timezone.utc
    )


def test_parse_easyrsa_expiry_rejects_garbage():
    assert parse_easyrsa_expiry("") is None
    assert parse_easyrsa_expiry("not-a-date") is None
    assert parse_easyrsa_expiry("360405210223") is None


def test_days_remaining_counts_down_from_notafter():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert days_remaining_until(now + timedelta(days=42), now=now) == 42


def test_days_remaining_is_zero_once_expired():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert days_remaining_until(now - timedelta(days=1), now=now) == 0


def test_days_remaining_treats_naive_values_as_utc():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert days_remaining_until(datetime(2026, 3, 2), now=now) == 60


def test_days_remaining_without_expiry_is_unknown():
    assert days_remaining_until(None) is None


def test_cert_expiry_map_skips_revoked_and_keeps_latest_per_cn():
    expiry_by_cn = cert_expiry_map_by_cn(parse_easyrsa_index(SAMPLE_INDEX))
    assert "revoked-client" not in expiry_by_cn
    assert expiry_by_cn["alice"] == datetime(2036, 4, 5, 21, 2, 23, tzinfo=timezone.utc)
    assert expiry_by_cn["bob"] == datetime(2027, 1, 1, tzinfo=timezone.utc)


def _adapter_with_profile(pem_marker: str) -> MagicMock:
    adapter = MagicMock()
    adapter.get_profile_files.return_value = [{"path": "/client/openvpn/vpn/alice.ovpn"}]
    adapter.read_profile_file.return_value = (
        f"client\n<cert>\n-----BEGIN CERTIFICATE-----\n{pem_marker}\n"
        "-----END CERTIFICATE-----\n</cert>\n"
    )
    return adapter


def test_refresh_config_cert_expiry_stores_naive_utc(monkeypatch):
    monkeypatch.setattr(
        "app.services.openvpn_cert.cert_not_after_utc",
        lambda pem: datetime(2035, 8, 28, 11, 53, 22, tzinfo=timezone.utc),
    )
    config = MagicMock()
    config.vpn_type = VpnType.openvpn
    config.client_name = "alice"
    config.cert_expires_at = None

    refresh_config_cert_expiry(config, _adapter_with_profile("MIIB"))

    assert config.cert_expires_at == datetime(2035, 8, 28, 11, 53, 22)


def test_refresh_config_cert_expiry_ignores_wireguard():
    config = MagicMock()
    config.vpn_type = VpnType.wireguard
    config.cert_expires_at = None
    adapter = MagicMock()

    refresh_config_cert_expiry(config, adapter)

    assert config.cert_expires_at is None
    adapter.get_profile_files.assert_not_called()


def test_refresh_config_cert_expiry_keeps_previous_value_when_node_unreachable():
    previous = datetime(2030, 1, 1)
    config = MagicMock()
    config.vpn_type = VpnType.openvpn
    config.client_name = "alice"
    config.cert_expires_at = previous
    adapter = MagicMock()
    adapter.get_profile_files.side_effect = RuntimeError("node down")

    refresh_config_cert_expiry(config, adapter)

    assert config.cert_expires_at == previous


def test_parse_iso_expiry_from_agent_payload():
    from app.services.openvpn_cert import expiry_map_from_iso_dict, parse_iso_expiry

    assert parse_iso_expiry("2036-07-09T11:10:29Z") == datetime(
        2036, 7, 9, 11, 10, 29, tzinfo=timezone.utc
    )
    mapped = expiry_map_from_iso_dict(
        {"alice": "2036-07-09T11:10:29Z", "bob": "bad", "": "2030-01-01T00:00:00Z"}
    )
    assert list(mapped) == ["alice"]
    assert mapped["alice"].year == 2036


def test_remote_adapter_expiry_map_falls_back_to_index(monkeypatch):
    from fastapi import HTTPException

    from app.services.node_adapter import RemoteNodeAdapter

    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)
    calls: list[str] = []

    def fake_request(method, path, **kwargs):
        calls.append(path)
        if path == "/openvpn/certs/expiry":
            raise HTTPException(status_code=404, detail="not found")
        if path == "/openvpn/easyrsa3/index":
            return {
                "content": (
                    "V\t360405210223Z\t\tC9014ACA2099B8A6FB3F856105979E79\tunknown\t/CN=alice\n"
                )
            }
        raise AssertionError(path)

    monkeypatch.setattr(adapter, "_request", fake_request)
    expiry = adapter.get_openvpn_cert_expiry_map()
    assert calls == ["/openvpn/certs/expiry", "/openvpn/easyrsa3/index"]
    assert "alice" in expiry
    assert expiry["alice"].year == 2036


def test_remote_adapter_expiry_map_uses_batch_endpoint(monkeypatch):
    from app.services.node_adapter import RemoteNodeAdapter

    adapter = RemoteNodeAdapter("10.0.0.2", 9100, "k" * 32, mtls_enabled=False)

    def fake_request(method, path, **kwargs):
        assert path == "/openvpn/certs/expiry"
        return {"expires_by_cn": {"alice": "2036-07-09T11:10:29Z"}}

    monkeypatch.setattr(adapter, "_request", fake_request)
    expiry = adapter.get_openvpn_cert_expiry_map()
    assert expiry["alice"] == datetime(2036, 7, 9, 11, 10, 29, tzinfo=timezone.utc)
