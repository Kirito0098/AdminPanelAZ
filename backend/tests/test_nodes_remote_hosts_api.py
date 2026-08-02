from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.openvpn_remote_hosts import (
    RemoteHostsError,
    hosts_to_json,
    normalize_hosts,
    parse_hosts_json,
    sync_openvpn_host_from_remotes,
)


def test_parse_roundtrip():
    raw = hosts_to_json(["1.1.1.1", "vpn.example.com"])
    assert parse_hosts_json(raw) == ["1.1.1.1", "vpn.example.com"]
    assert parse_hosts_json(None) == []
    assert parse_hosts_json("not-json") == []


def test_put_logic_empty_skips_setup():
    """Empty list normalizes to [] and means openvpn_remote_hosts=None in the router."""
    assert normalize_hosts([]) == []


def test_put_rejects_dup():
    with pytest.raises(RemoteHostsError):
        normalize_hosts(["a.com", "A.com"])


def test_sync_skips_when_empty():
    factory = MagicMock()
    assert sync_openvpn_host_from_remotes(factory, []) == []
    factory.assert_not_called()


def test_sync_best_effort_warning():
    adapter = MagicMock()
    adapter.update_antizapret_settings.side_effect = RuntimeError("down")
    warnings = sync_openvpn_host_from_remotes(lambda: adapter, ["1.2.3.4"])
    assert warnings and "OPENVPN_HOST" in warnings[0]


def test_sync_sets_first_host():
    adapter = MagicMock()
    assert sync_openvpn_host_from_remotes(lambda: adapter, ["1.2.3.4", "vpn.example.com"]) == []
    adapter.update_antizapret_settings.assert_called_once_with({"openvpn_host": "1.2.3.4"})


def test_sync_adapter_resolve_failure_yields_warning():
    """Missing remote API key (HTTP 503 from get_adapter_for_node) must not escape as 503."""

    def boom():
        raise HTTPException(status_code=503, detail="API-ключ узла 'x' недоступен")

    warnings = sync_openvpn_host_from_remotes(boom, ["1.2.3.4"])
    assert len(warnings) == 1
    assert "OPENVPN_HOST" in warnings[0]
    assert "недоступен" in warnings[0]
