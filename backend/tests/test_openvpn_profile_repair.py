"""Tests for OpenVPN profile helpers (no automatic cert re-issue)."""

from unittest.mock import MagicMock

from app.services.openvpn_pki import ProfileCertIssue, ProfileValidationResult
from app.services.openvpn_profile_repair import (
    recreate_openvpn_profiles,
    recreate_openvpn_profiles_after_admin_change,
    validate_openvpn_profiles,
)


def test_recreate_openvpn_profiles_calls_client_sh_7_only():
    adapter = MagicMock()

    result = recreate_openvpn_profiles(adapter)

    adapter.recreate_profiles.assert_called_once()
    adapter.add_openvpn_client.assert_not_called()
    assert result.success
    assert result.recreated


def test_recreate_openvpn_profiles_after_admin_change_does_not_reissue(monkeypatch):
    adapter = MagicMock()
    monkeypatch.setattr(
        "app.services.openvpn_profile_repair.validate_client_profiles",
        lambda *args, **kwargs: ProfileValidationResult(
            ready=False,
            issues=(
                ProfileCertIssue(
                    client_name="AN_Claymore",
                    path="/root/antizapret/client/openvpn/antizapret-udp/x.ovpn",
                    filename="x.ovpn",
                    serial_hex="F401806F35A8048BA0941A9F085EF9C2",
                    status="revoked",
                ),
            ),
        ),
    )

    result = recreate_openvpn_profiles_after_admin_change(adapter, client_names=["AN_Claymore"])

    adapter.recreate_profiles.assert_called_once()
    adapter.add_openvpn_client.assert_not_called()
    assert result.success
    assert result.validation is not None
    assert not result.validation.ready


def test_validate_openvpn_profiles_is_read_only(monkeypatch):
    adapter = MagicMock()
    monkeypatch.setattr(
        "app.services.openvpn_profile_repair.validate_client_profiles",
        lambda *args, **kwargs: ProfileValidationResult(ready=True, issues=()),
    )

    result = validate_openvpn_profiles(adapter, client_names=["client-a"])

    adapter.recreate_profiles.assert_not_called()
    adapter.add_openvpn_client.assert_not_called()
    assert result.ready
