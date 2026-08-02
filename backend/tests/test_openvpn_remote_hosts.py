import pytest

from app.services.openvpn_remote_hosts import (
    RemoteHostsError,
    apply_openvpn_remote_hosts,
    normalize_hosts,
    validate_host,
)

SAMPLE = """client
dev tun
remote 10.0.0.1 1194 udp
remote 10.0.0.1 443 tcp
<ca>
-----BEGIN CERTIFICATE-----
ABC
-----END CERTIFICATE-----
</ca>
setenv FRIENDLY_NAME test
"""


def test_validate_host_ok():
    assert validate_host(" 1.2.3.4 ") == "1.2.3.4"
    assert validate_host("vpn.example.com") == "vpn.example.com"


def test_validate_host_rejects_bad():
    with pytest.raises(RemoteHostsError):
        validate_host("")
    with pytest.raises(RemoteHostsError):
        validate_host("bad host")
    with pytest.raises(RemoteHostsError):
        validate_host("http://evil")


def test_normalize_max_and_dup():
    assert normalize_hosts(None) == []
    assert normalize_hosts([]) == []
    with pytest.raises(RemoteHostsError):
        normalize_hosts(["a.com", "a.com"])
    with pytest.raises(RemoteHostsError):
        normalize_hosts([f"h{i}.com" for i in range(9)])


def test_apply_expands_hosts_times_ports():
    out = apply_openvpn_remote_hosts(SAMPLE, ["1.1.1.1", "2.2.2.2", "3.3.3.3"])
    remotes = [ln for ln in out.splitlines() if ln.startswith("remote ")]
    assert remotes == [
        "remote 1.1.1.1 1194 udp",
        "remote 1.1.1.1 443 tcp",
        "remote 2.2.2.2 1194 udp",
        "remote 2.2.2.2 443 tcp",
        "remote 3.3.3.3 1194 udp",
        "remote 3.3.3.3 443 tcp",
    ]
    assert "FRIENDLY_NAME" in out
    assert "BEGIN CERTIFICATE" in out


def test_apply_empty_hosts_unchanged():
    assert apply_openvpn_remote_hosts(SAMPLE, []) == SAMPLE


def test_apply_no_remote_unchanged():
    body = "client\ndev tun\n"
    assert apply_openvpn_remote_hosts(body, ["1.1.1.1"]) == body


def test_apply_idempotent():
    once = apply_openvpn_remote_hosts(SAMPLE, ["a.com", "b.com"])
    twice = apply_openvpn_remote_hosts(once, ["a.com", "b.com"])
    assert once == twice
