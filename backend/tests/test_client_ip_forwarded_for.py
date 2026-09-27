"""Client IP behind a trusted proxy: nginx appends $remote_addr, so the leftmost XFF entry is client-controlled."""

from types import SimpleNamespace

import pytest

from app.services.ip_restriction import IpRestrictionService


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(trusted_proxy_ip_list=["127.0.0.1", "10.0.0.2"]),
    )
    return IpRestrictionService()


def _request(peer: str, forwarded: str | None = None):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_spoofed_leftmost_entry_is_ignored(service):
    request = _request("127.0.0.1", "198.51.100.7, 203.0.113.5")
    assert service.get_client_ip(request) == "203.0.113.5"


def test_trusted_hops_are_skipped_from_the_right(service):
    request = _request("127.0.0.1", "198.51.100.7, 203.0.113.5, 10.0.0.2")
    assert service.get_client_ip(request) == "203.0.113.5"


def test_single_entry_from_trusted_proxy(service):
    assert service.get_client_ip(_request("::ffff:127.0.0.1", "203.0.113.5")) == "203.0.113.5"


def test_untrusted_peer_ignores_forwarded_for(service):
    assert service.get_client_ip(_request("203.0.113.9", "198.51.100.7")) == "203.0.113.9"


def test_all_trusted_chain_falls_back_to_leftmost(service):
    assert service.get_client_ip(_request("127.0.0.1", "10.0.0.2, 127.0.0.1")) == "10.0.0.2"


def test_empty_forwarded_for_uses_peer(service):
    assert service.get_client_ip(_request("127.0.0.1", " , ")) == "127.0.0.1"


@pytest.mark.parametrize(
    ("client_ip", "expected"),
    [(None, "203.0.113.5"), ("192.0.2.44", "192.0.2.44")],
)
def test_geo_routing_hint_ignores_spoofed_forwarded_for(service, monkeypatch, client_ip, expected):
    from app.routers import nodes

    seen = {}
    monkeypatch.setattr(nodes, "build_geo_routing_hint", lambda _db, client_ip: seen.setdefault("ip", client_ip))
    request = _request("127.0.0.1", "198.51.100.7, 203.0.113.5")
    nodes.geo_routing_hint(request=request, client_ip=client_ip, _=None, db=None)
    assert seen["ip"] == expected
