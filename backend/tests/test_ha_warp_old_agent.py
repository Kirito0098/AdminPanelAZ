"""WARP choice values must reach node agents of 2.25.1 unchanged in meaning.

Old agents know ``ANTIZAPRET_WARP``/``VPN_WARP`` as y/n flags and write
``normalize_flag(value)``: ``"1"`` (None) became ``y`` and ``"2"`` (All) became ``n``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.antizapret_settings import normalize_flag, read_antizapret_settings, update_antizapret_settings
from app.services.node_adapter import RemoteNodeAdapter
from app.services.node_sync import antizapret_sync

_OLD_AGENT_FLAG_KEYS = ("ANTIZAPRET_WARP", "VPN_WARP", "route_all")


def _old_agent_write(payload: dict) -> dict[str, str]:
    return {key: normalize_flag(value) for key, value in payload.items() if key in _OLD_AGENT_FLAG_KEYS}


def _sent_payload(updates: dict) -> dict:
    adapter = RemoteNodeAdapter(host="127.0.0.1", port=9100, api_key="k" * 32)
    adapter._request = MagicMock(return_value={"success": True, "warnings": []})
    adapter.update_antizapret_settings(updates)
    method, path = adapter._request.call_args.args
    assert (method, path) == ("PUT", "/routing/antizapret-settings")
    return adapter._request.call_args.kwargs["json"]


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"ANTIZAPRET_WARP": "1", "VPN_WARP": "2"}, {"ANTIZAPRET_WARP": "n", "VPN_WARP": "y"}),
        ({"ANTIZAPRET_WARP": "2", "VPN_WARP": "1"}, {"ANTIZAPRET_WARP": "y", "VPN_WARP": "n"}),
    ],
)
def test_old_agent_writes_requested_warp_mode(updates, expected):
    assert _old_agent_write(_sent_payload(updates)) == expected


@pytest.mark.parametrize("initial", ["ANTIZAPRET_WARP=3\nVPN_WARP=2\n", "ANTIZAPRET_WARP=y\nVPN_WARP=y\n"])
def test_new_agent_reads_back_requested_warp_mode(tmp_path: Path, initial: str):
    setup = tmp_path / "setup"
    setup.write_text(initial, encoding="utf-8")

    update_antizapret_settings(setup, _sent_payload({"ANTIZAPRET_WARP": "1", "VPN_WARP": "1"}))
    settings = read_antizapret_settings(setup)
    assert (settings["ANTIZAPRET_WARP"], settings["VPN_WARP"]) == ("1", "1")

    update_antizapret_settings(setup, _sent_payload({"ANTIZAPRET_WARP": "2", "VPN_WARP": "2"}))
    settings = read_antizapret_settings(setup)
    assert (settings["ANTIZAPRET_WARP"], settings["VPN_WARP"]) == ("2", "2")


def test_numeric_setup_keeps_numeric_format(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.write_text("ANTIZAPRET_WARP=3\nVPN_WARP=1\n", encoding="utf-8")
    update_antizapret_settings(setup, _sent_payload({"ANTIZAPRET_WARP": "2", "VPN_WARP": "2"}))
    assert setup.read_text(encoding="utf-8") == "ANTIZAPRET_WARP=2\nVPN_WARP=2\n"


def test_selective_modes_and_other_keys_sent_as_is():
    assert _sent_payload({"ANTIZAPRET_WARP": "3", "route_all": "y", "openvpn_host": "vpn.example.com"}) == {
        "ANTIZAPRET_WARP": "3",
        "route_all": "y",
        "openvpn_host": "vpn.example.com",
    }
    assert _sent_payload({"ANTIZAPRET_WARP": "4"}) == {"ANTIZAPRET_WARP": "4"}
    assert _sent_payload({"VPN_WARP": "bogus"}) == {"VPN_WARP": "bogus"}


def _replica(node_id: int, name: str) -> MagicMock:
    node = MagicMock()
    node.id = node_id
    node.name = name
    return node


def _replicate(monkeypatch, adapters: dict[int, MagicMock], updates: dict):
    replicas = [_replica(node_id, f"replica-{node_id}") for node_id in adapters]
    monkeypatch.setattr(antizapret_sync, "is_auto_sync_enabled", lambda _group: True)
    monkeypatch.setattr(antizapret_sync, "get_replica_nodes", lambda _db, _group: replicas)
    monkeypatch.setattr(antizapret_sync, "get_adapter_for_node", lambda node: adapters[node.id])
    finalize = MagicMock()
    monkeypatch.setattr(antizapret_sync, "finalize_replicate_outcome", finalize)
    return antizapret_sync.replicate_antizapret_settings(MagicMock(), MagicMock(), updates)


def test_replica_with_old_agent_and_selective_mode_is_reported(monkeypatch):
    old_agent = MagicMock()
    old_agent.get_antizapret_settings.return_value = {"ANTIZAPRET_WARP": "n", "VPN_WARP": "n"}
    new_agent = MagicMock()
    new_agent.get_antizapret_settings.return_value = {"ANTIZAPRET_WARP": "3", "VPN_WARP": "1"}

    result = _replicate(monkeypatch, {2: old_agent, 3: new_agent}, {"ANTIZAPRET_WARP": "3", "VPN_WARP": "1"})

    assert [entry["node_id"] for entry in result.errors] == [2]
    assert "ANTIZAPRET_WARP" in result.errors[0]["error"]
    assert "node agent" in result.errors[0]["error"]
    assert [entry["node_id"] for entry in result.successes] == [3]


def test_replica_settings_without_choice_keys_are_not_read_back(monkeypatch):
    agent = MagicMock()

    result = _replicate(monkeypatch, {2: agent}, {"route_all": "y"})

    assert result.errors == []
    agent.get_antizapret_settings.assert_not_called()
