from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models import Node, NodeStatus
from app.services import awg2 as awg2_mod
from app.services import user_provisioning as up
from app.services.user_provisioning import ACTION_CREATE, PlanItem, _is_node_unreachable


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

    monkeypatch.setattr("app.services.node_manager.get_adapter_for_node", fake_adapter)

    with pytest.raises(HTTPException) as ei:
        awg2_mod.assert_awg2_available_on_nodes([good, bad])
    assert ei.value.status_code == 409
    detail = ei.value.detail
    assert isinstance(detail, dict)
    assert "Test_serv" in detail["message"]
    assert "Germani" not in detail["message"]
    assert "install_command" in detail


def test_assert_awg2_available_ok_when_all_installed(monkeypatch):
    nodes = [_vpn_node(1, "A"), _vpn_node(2, "B")]

    def fake_adapter(node):
        ad = MagicMock()
        ad.get_awg2_health.return_value = {"installed": True}
        return ad

    monkeypatch.setattr("app.services.node_manager.get_adapter_for_node", fake_adapter)
    awg2_mod.assert_awg2_available_on_nodes(nodes)  # no raise


def test_apply_node_continues_after_awg2_not_installed(monkeypatch):
    session = MagicMock()
    owner = MagicMock()
    actor = MagicMock()
    node = MagicMock()
    node.name = "Test_serv"
    session.get.return_value = node

    items = [
        PlanItem(node_id=2, node_label="Test_serv", client_name="node", vpn_type="amneziawg2", action=ACTION_CREATE),
        PlanItem(node_id=2, node_label="Test_serv", client_name="node", vpn_type="openvpn", action=ACTION_CREATE),
    ]

    calls = {"n": 0}

    def fake_apply_create(session, node, item, owner, actor):
        calls["n"] += 1
        if item.vpn_type == "amneziawg2":
            return {
                "node_id": 2,
                "node_label": "Test_serv",
                "client_name": item.client_name,
                "vpn_type": item.vpn_type,
                "action": ACTION_CREATE,
                "status": "error",
                "error": "409: AZ-AWG2 не установлен",
            }
        return {
            "node_id": 2,
            "node_label": "Test_serv",
            "client_name": item.client_name,
            "vpn_type": item.vpn_type,
            "action": ACTION_CREATE,
            "status": "done",
            "error": None,
        }

    monkeypatch.setattr(up, "_apply_create", fake_apply_create)
    results = up._apply_node(2, items, session, owner, actor)
    assert calls["n"] == 2
    assert results[0]["status"] == "error"
    assert results[1]["status"] == "done"
    assert results[1].get("error") != "Пропущено после сетевой ошибки на узле"


def test_is_node_unreachable_409_false():
    assert _is_node_unreachable(HTTPException(status_code=409, detail="conflict")) is False


def test_is_node_unreachable_502_true():
    assert _is_node_unreachable(HTTPException(status_code=502, detail="bad gateway")) is True


def test_apply_node_skips_after_unreachable(monkeypatch):
    session = MagicMock()
    owner = MagicMock()
    actor = MagicMock()
    node = MagicMock()
    node.name = "Test_serv"
    session.get.return_value = node

    items = [
        PlanItem(node_id=2, node_label="Test_serv", client_name="a", vpn_type="openvpn", action=ACTION_CREATE),
        PlanItem(node_id=2, node_label="Test_serv", client_name="b", vpn_type="wireguard", action=ACTION_CREATE),
    ]

    calls = {"n": 0}

    def fake_apply_create(session, node, item, owner, actor):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "node_id": 2,
                "node_label": "Test_serv",
                "client_name": item.client_name,
                "vpn_type": item.vpn_type,
                "action": ACTION_CREATE,
                "status": "error",
                "error": "502: gateway",
                "unreachable": True,
            }
        return {
            "node_id": 2,
            "node_label": "Test_serv",
            "client_name": item.client_name,
            "vpn_type": item.vpn_type,
            "action": ACTION_CREATE,
            "status": "done",
            "error": None,
        }

    monkeypatch.setattr(up, "_apply_create", fake_apply_create)
    results = up._apply_node(2, items, session, owner, actor)
    assert calls["n"] == 1
    assert results[0]["status"] == "error"
    assert results[0].get("unreachable") is True
    assert results[1]["status"] == "skipped"
    assert results[1]["error"] == "Пропущено после сетевой ошибки на узле"
