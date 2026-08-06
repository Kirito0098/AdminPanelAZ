from app.services.client_local_ip import (
    normalize_tunnel_ip,
    parse_wireguard_allowed_ips_by_client,
)


def test_normalize_tunnel_ip_strips_cidr_and_port():
    assert normalize_tunnel_ip("10.8.0.2/32") == "10.8.0.2"
    assert normalize_tunnel_ip("10.0.0.2:1194") == "10.0.0.2"
    assert normalize_tunnel_ip("10.1.0.2/32, 10.2.0.2/32") == "10.1.0.2, 10.2.0.2"
    assert normalize_tunnel_ip("(none)") is None
    assert normalize_tunnel_ip("") is None


def test_parse_wireguard_allowed_ips_by_client():
    content = """
[Interface]
Address = 10.8.0.1/24

# Client = Alice
[Peer]
PublicKey = aaa
AllowedIPs = 10.8.0.2/32

# Client = Bob
[Peer]
PublicKey = bbb
AllowedIPs = 10.8.0.3/32, 10.9.0.3/32
"""
    parsed = parse_wireguard_allowed_ips_by_client(content)
    assert parsed["alice"] == ["10.8.0.2"]
    assert parsed["bob"] == ["10.8.0.3", "10.9.0.3"]
