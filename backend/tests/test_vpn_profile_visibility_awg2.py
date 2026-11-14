from app.services.vpn_profile_visibility import (
    filter_profile_files,
    normalize_policy,
    profile_file_allowed,
)


def test_normalize_defaults_awg2_tunnel_only_true():
    p = normalize_policy({"routes": ["az"], "protocols": ["amneziawg2"], "openvpn_groups": []})
    assert p["awg2_tunnel_only"] is True


def test_awg2_tunnel_only_hides_sidecars():
    policy = normalize_policy(
        {
            "routes": ["az", "vpn"],
            "protocols": ["amneziawg2"],
            "openvpn_groups": [],
            "awg2_tunnel_only": True,
        }
    )
    files = [
        {"protocol": "amneziawg2", "variant": "antizapret", "path": "/x/az-name-am.conf"},
        {"protocol": "amneziawg2", "variant": "antizapret", "path": "/x/az-name.vpn", "kind": "vpnuri"},
        {"protocol": "amneziawg2", "variant": "antizapret", "path": "/x/az-name-vpnuri.txt", "kind": "vpnuri"},
    ]
    out = filter_profile_files(files, policy)
    assert [f["path"] for f in out] == ["/x/az-name-am.conf"]


def test_awg2_tunnel_only_false_keeps_sidecars():
    policy = normalize_policy(
        {
            "routes": ["az"],
            "protocols": ["amneziawg2"],
            "openvpn_groups": [],
            "awg2_tunnel_only": False,
        }
    )
    assert profile_file_allowed(
        policy, protocol="amneziawg2", variant="antizapret", path="/x/a.vpn", kind="vpnuri"
    )
