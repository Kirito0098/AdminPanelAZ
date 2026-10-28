from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models import Node, NodeStatus
from app.services import awg2 as awg2_mod


def _vpn_node(id_: int, name: str) -> Node:
    return Node(
        id=id_,
        name=name,
        host=f"{id_}.example",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=False,
        node_kind="vpn",
        node_metadata="{}",
    )


def test_assert_awg2_available_raises_listing_missing_nodes(monkeypatch):
    good = _vpn_node(1, "Germani")
    bad = _vpn_node(2, "Test_serv")

    def fake_adapter(node):
        ad = MagicMock()
        ad.get_awg2_health.return_value = {"installed": node.id == 1}
        return ad

    monkeypatch.setattr(awg2_mod, "get_adapter_for_node", fake_adapter)

    with pytest.raises(HTTPException) as ei:
        awg2_mod.assert_awg2_available_on_nodes([good, bad])
    assert ei.value.status_code == 409
    detail = ei.value.detail
    assert isinstance(detail, dict)
    assert "Test_serv" in detail["message"]
    assert "Germani" not in detail["message"] or "Test_serv" in detail["message"]
    assert "install_command" in detail


def test_assert_awg2_available_ok_when_all_installed(monkeypatch):
    nodes = [_vpn_node(1, "A"), _vpn_node(2, "B")]

    def fake_adapter(node):
        ad = MagicMock()
        ad.get_awg2_health.return_value = {"installed": True}
        return ad

    monkeypatch.setattr(awg2_mod, "get_adapter_for_node", fake_adapter)
    awg2_mod.assert_awg2_available_on_nodes(nodes)  # no raise
