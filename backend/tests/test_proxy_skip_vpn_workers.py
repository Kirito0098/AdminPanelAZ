"""Proxy nodes must not be polled with the VPN adapter in background jobs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models import NodeStatus

from app.services import cert_sync_worker as cert_sync
from app.services import geo_routing_hint as geo_hint
from app.services import traffic_limit_reconcile as traffic_limit
from app.services import user_reminder_service as reminders
from app.services import wg_policy_sync_worker as wg_sync
from app.services.cidr.pipeline import orchestrator as cidr_orch


def _proxy(**kwargs):
    defaults = dict(id=9, name="VK", node_kind="proxy", status="online")
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _vpn(**kwargs):
    defaults = dict(id=1, name="vpn1", node_kind="vpn", status="online")
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_list_vpn_nodes_drops_proxy():
    from app.services.node_manager import list_vpn_nodes

    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = [_vpn(), _proxy()]
    names = [n.name for n in list_vpn_nodes(db)]
    assert names == ["vpn1"]


def test_traffic_limit_reconcile_skips_proxy(monkeypatch):
    db = MagicMock()
    db.query.return_value.all.return_value = [_proxy()]
    get_adapter = MagicMock(side_effect=AssertionError("vpn adapter"))
    monkeypatch.setattr(traffic_limit, "get_adapter_for_node", get_adapter)
    result = traffic_limit.reconcile_traffic_limit_policies(db)
    get_adapter.assert_not_called()
    assert result["changed"] == 0


def test_wg_policy_sync_skips_proxy(monkeypatch):
    db = MagicMock()
    db.query.return_value.all.return_value = [_proxy()]
    get_adapter = MagicMock(side_effect=AssertionError("vpn adapter"))
    monkeypatch.setattr(wg_sync, "get_adapter_for_node", get_adapter)
    result = wg_sync.reconcile_wg_policies_for_all_nodes(db)
    get_adapter.assert_not_called()
    assert result["nodes_processed"] == 0


def test_user_reminders_skips_proxy(monkeypatch):
    db = MagicMock()
    db.query.return_value.all.return_value = [_proxy()]
    monkeypatch.setattr(reminders, "self_service_reminder_enabled", lambda: True)
    get_adapter = MagicMock(side_effect=AssertionError("vpn adapter"))
    monkeypatch.setattr(reminders, "get_adapter_for_node", get_adapter)
    sent = reminders.process_user_reminders(db)
    get_adapter.assert_not_called()
    assert sent == 0


def test_geo_routing_hint_skips_proxy_adapter(monkeypatch):
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = [_proxy()]
    get_adapter = MagicMock(side_effect=AssertionError("vpn adapter"))
    monkeypatch.setattr(geo_hint, "get_adapter_for_node", get_adapter)
    monkeypatch.setattr(geo_hint, "lookup_ip_geo", lambda *_a, **_k: {})
    monkeypatch.setattr(geo_hint, "lookup_ips_geo", lambda *_a, **_k: {})
    hint = geo_hint.build_geo_routing_hint(db)
    get_adapter.assert_not_called()
    assert hint.nodes == [] or all(getattr(n, "node_id", None) != 9 for n in getattr(hint, "nodes", []))


def test_cert_sync_skips_proxy(monkeypatch):
    db = MagicMock()
    db.query.return_value.all.return_value = [_proxy()]
    get_adapter = MagicMock(side_effect=AssertionError("vpn adapter"))
    monkeypatch.setattr(cert_sync, "get_adapter_for_node", get_adapter)
    updated = cert_sync.sync_cert_expiry(db)
    get_adapter.assert_not_called()
    assert updated == 0


def test_cidr_all_online_skips_proxy():
    proxy = _proxy(status=SimpleNamespace(value="online"))
    vpn = _vpn(status=SimpleNamespace(value="online"))
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [vpn, proxy]
    nodes, skipped = cidr_orch.resolve_deploy_targets(db, all_online=True)
    assert [n.name for n in nodes] == ["vpn1"]
    assert any(item.get("node_name") == "VK" for item in skipped)
