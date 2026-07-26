"""QR profile vs download-link selection."""

from pathlib import Path

import pytest

from app.services.qr_generator import (
    PRACTICAL_QR_PROFILE_MAX_BYTES,
    fits_in_qr,
    generate_qr_png,
    prefers_download_link_qr,
)


def test_short_wireguard_fits_as_profile():
    content = (
        "[Interface]\nPrivateKey = abc\nAddress = 10.0.0.2/32\n\n"
        "[Peer]\nPublicKey = xyz\nEndpoint = vpn.example:51820\n"
        "AllowedIPs = 0.0.0.0/0\n"
    )
    assert fits_in_qr(content)
    assert not prefers_download_link_qr(
        path="/root/antizapret/client/wireguard/vpn/vpn-client-wg.conf",
        content=content,
    )
    assert generate_qr_png(content).startswith(b"\x89PNG")


def test_oversized_content_prefers_download_link():
    content = "x" * (PRACTICAL_QR_PROFILE_MAX_BYTES + 50)
    assert not fits_in_qr(content)
    assert prefers_download_link_qr(path="/tmp/short-name.conf", content=content)


def test_absolute_qr_overflow_prefers_download_link():
    content = "y" * 4000
    assert not fits_in_qr(content)
    with pytest.raises(ValueError, match="слишком длинная"):
        generate_qr_png(content)


def test_az_wireguard_path_always_download_link_even_if_short():
    content = "[Interface]\nPrivateKey = abc\nAddress = 10.0.0.2/32\n"
    assert fits_in_qr(content)
    assert prefers_download_link_qr(
        path="/root/antizapret/client/wireguard/antizapret/antizapret-client-wg.conf",
        content=content,
    )


def test_az_amneziawg_path_always_download_link():
    content = "[Interface]\nPrivateKey = abc\nAddress = 10.0.0.2/32\n"
    assert prefers_download_link_qr(
        path="/root/antizapret/client/amneziawg/antizapret/antizapret-client-am.conf",
        content=content,
    )


def test_openvpn_always_download_link():
    content = "client\ndev tun\n" + ("# pad\n" * 20)
    assert prefers_download_link_qr(
        path="/root/antizapret/client/openvpn/vpn/vpn-client.ovpn",
        content=content,
    )


def test_install_root_antizapret_name_does_not_false_positive_vpn_wg():
    """Path contains '/root/antizapret/' but file is VPN route — may still embed if small."""
    content = (
        "[Interface]\nPrivateKey = abc\nAddress = 10.0.0.2/32\n\n"
        "[Peer]\nPublicKey = xyz\nEndpoint = vpn.example:51820\nAllowedIPs = 0.0.0.0/0\n"
    )
    assert not prefers_download_link_qr(
        path="/root/antizapret/client/wireguard/vpn/vpn-client-wg.conf",
        content=content,
    )


@pytest.mark.parametrize(
    "rel",
    [
        "wireguard/antizapret/antizapret-123-(vpn.claymore-it.ru)-wg.conf",
        "amneziawg/antizapret/antizapret-123-(vpn.claymore-it.ru)-am.conf",
        "openvpn/antizapret/antizapret-AN_Claymore-(vpn.claymore-it.ru).ovpn",
    ],
)
def test_real_az_disk_profiles_prefer_download_link(rel: str):
    path = Path("/root/antizapret/client") / rel
    if not path.is_file():
        pytest.skip(f"missing sample profile {path}")
    content = path.read_text(encoding="utf-8", errors="replace")
    assert prefers_download_link_qr(path=str(path), content=content)
