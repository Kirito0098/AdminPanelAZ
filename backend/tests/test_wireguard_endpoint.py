from app.services.wireguard_endpoint import apply_wireguard_endpoint_host

SAMPLE = """[Interface]
PrivateKey=abc
[Peer]
Endpoint = 10.0.0.1:51820
AllowedIPs = 0.0.0.0/0
"""


def test_replaces_endpoint_keeps_port():
    out = apply_wireguard_endpoint_host(SAMPLE, "1.2.3.4")
    assert "Endpoint = 1.2.3.4:51820" in out
    assert "10.0.0.1" not in out


def test_empty_host_unchanged():
    assert apply_wireguard_endpoint_host(SAMPLE, "") == SAMPLE


def test_no_endpoint_unchanged():
    body = "[Interface]\nPrivateKey=x\n"
    assert apply_wireguard_endpoint_host(body, "1.1.1.1") == body
