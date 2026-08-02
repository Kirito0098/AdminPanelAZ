"""Disk patch of OpenVPN remotes after client.sh 7 (stage 06a)."""

from unittest.mock import MagicMock

from app.services.profile_delivery import patch_openvpn_profiles_on_node


def test_patch_writes_when_hosts():
    adapter = MagicMock()
    adapter.list_openvpn_clients.return_value = ["alice"]
    adapter.get_profile_files.return_value = [{"path": "/x/alice.ovpn"}]
    adapter.read_profile_file.return_value = "remote 10.0.0.1 1194 udp\n"
    result = patch_openvpn_profiles_on_node(adapter, ["1.1.1.1", "2.2.2.2"])
    assert result["patched"] == 1
    adapter.write_profile_file.assert_called()
    written = adapter.write_profile_file.call_args[0][1]
    assert "remote 1.1.1.1 1194 udp" in written
    assert "remote 2.2.2.2 1194 udp" in written


def test_patch_noop_empty_hosts():
    adapter = MagicMock()
    assert patch_openvpn_profiles_on_node(adapter, [])["patched"] == 0
    adapter.list_openvpn_clients.assert_not_called()


def test_recreate_openvpn_profiles_patches_when_hosts():
    from app.services.openvpn_profile_repair import recreate_openvpn_profiles

    adapter = MagicMock()
    adapter.recreate_profiles.return_value = "ok"
    adapter.list_openvpn_clients.return_value = ["alice"]
    adapter.get_profile_files.return_value = [{"path": "/x/alice.ovpn"}]
    adapter.read_profile_file.return_value = "remote 10.0.0.1 1194 udp\n"

    result = recreate_openvpn_profiles(adapter, hosts=["1.1.1.1"])

    assert result.success
    assert result.recreated
    assert result.patch is not None
    assert result.patch["patched"] == 1
    adapter.write_profile_file.assert_called_once()


def test_recreate_openvpn_profiles_skips_patch_without_hosts():
    from app.services.openvpn_profile_repair import recreate_openvpn_profiles

    adapter = MagicMock()
    adapter.recreate_profiles.return_value = "ok"

    result = recreate_openvpn_profiles(adapter)

    assert result.success
    assert result.patch is None
    adapter.list_openvpn_clients.assert_not_called()
