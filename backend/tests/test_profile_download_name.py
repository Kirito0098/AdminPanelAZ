from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files


def test_openvpn_antizapret_download_name():
    name = build_profile_download_filename(
        "AN_Herrington",
        protocol="openvpn",
        variant="antizapret",
        path="/root/antizapret/client/openvpn/antizapret/antizapret-AN_Herrington-(vpn.example.com).ovpn",
    )
    assert name == "AZ-AN_Herrington.ovpn"


def test_openvpn_vpn_download_name():
    name = build_profile_download_filename(
        "AN_Claymore",
        protocol="openvpn",
        variant="vpn",
        path="/root/antizapret/client/openvpn/vpn/vpn-AN_Claymore-(vpn.example.com).ovpn",
    )
    assert name == "VPN-AN_Claymore.ovpn"


def test_openvpn_udp_tcp_suffixes():
    udp = build_profile_download_filename(
        "client-1",
        protocol="openvpn",
        variant="antizapret-udp",
        path="/root/antizapret/client/openvpn/antizapret-udp/az-client-1-udp.ovpn",
    )
    tcp = build_profile_download_filename(
        "client_2",
        protocol="openvpn",
        variant="vpn-tcp",
        path="/root/antizapret/client/openvpn/vpn-tcp/vpn-client_2-tcp.ovpn",
    )
    assert udp == "AZ-client-1-udp.ovpn"
    assert tcp == "VPN-client_2-tcp.ovpn"


def test_wireguard_and_amneziawg_download_names():
    wg = build_profile_download_filename(
        "Test121",
        protocol="wireguard",
        variant="antizapret",
        path="/root/antizapret/client/wireguard/antizapret/antizapret-Test121-wg.conf",
    )
    awg = build_profile_download_filename(
        "Andrew-2",
        protocol="amneziawg",
        variant="vpn",
        path="/root/antizapret/client/amneziawg/vpn/vpn-Andrew-2-am.conf",
    )
    assert wg == "WG-AZ-Test121.conf"
    assert awg == "AWG-VPN-Andrew-2.conf"


def test_enrich_profile_files_adds_download_filename():
    files = enrich_profile_files(
        "AN_Herrington",
        [
            {
                "protocol": "openvpn",
                "variant": "antizapret",
                "filename": "antizapret-AN_Herrington-(vpn.example.com).ovpn",
                "path": "/root/antizapret/client/openvpn/antizapret/antizapret-AN_Herrington-(vpn.example.com).ovpn",
            }
        ],
    )
    assert files[0]["download_filename"] == "AZ-AN_Herrington.ovpn"
