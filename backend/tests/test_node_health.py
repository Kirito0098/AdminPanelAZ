"""Tests for node health payload and traffic worker integration."""

from unittest.mock import MagicMock, patch

import pytest


def test_build_health_payload_includes_service_counts():
    from app.services.node_health import NODE_AGENT_VERSION, build_health_payload

    service = MagicMock()
    service.base_path = "/root/antizapret"
    service.get_antizapret_version.return_value = "v1.2.3"
    service.get_server_ip.return_value = "203.0.113.10"
    service.get_service_status.return_value = [
        MagicMock(active=True),
        MagicMock(active=False),
        MagicMock(active=True),
    ]

    payload = build_health_payload(service)

    assert payload["antizapret_path"] == "/root/antizapret"
    assert payload["antizapret_version"] == "v1.2.3"
    assert payload["server_ip"] == "203.0.113.10"
    assert payload["services_active"] == 2
    assert payload["services_total"] == 3
    assert payload["agent_version"] == NODE_AGENT_VERSION
    assert payload["hostname"]


def test_local_node_adapter_health_reports_node_agent_version():
    from unittest.mock import MagicMock

    from app.services.node_adapter import LocalNodeAdapter
    from app.services.node_health import NODE_AGENT_VERSION

    adapter = LocalNodeAdapter(service=MagicMock())
    adapter._service.base_path = "/root/antizapret"
    adapter._service.get_antizapret_version.return_value = "v1"
    adapter._service.get_server_ip.return_value = "10.0.0.1"
    adapter._service.get_service_status.return_value = []

    payload = adapter.health_check()

    assert payload["agent_version"] == NODE_AGENT_VERSION


def test_traffic_worker_uses_correct_adapter_signature():
    from app.services.traffic import worker

    node = MagicMock()
    node.id = 7
    node.name = "remote"

    adapter = MagicMock()
    adapter.parse_openvpn_status.return_value = []
    adapter.parse_wireguard_status.return_value = []

    db = MagicMock()
    db.query.return_value.all.return_value = [node]

    with patch.object(worker, "SessionLocal", return_value=db), patch.object(
        worker, "get_adapter_for_node", return_value=adapter
    ) as get_adapter, patch.object(worker, "TrafficCollectorService") as collector_cls, patch.object(
        worker.settings, "traffic_limit_reconcile_after_sync", False
    ):
        worker._collect_all_nodes()

    get_adapter.assert_called_once_with(node)


def test_update_node_from_health_persists_metadata_keys():
    from app.services.node_manager import update_node_from_health

    node = MagicMock()
    node.node_metadata = "{}"
    db = MagicMock()

    health = {
        "status": "online",
        "hostname": "vpn1",
        "server_ip": "10.0.0.1",
        "services_active": 4,
        "services_total": 6,
        "antizapret_version": "abc123",
    }

    update_node_from_health(node, health, db)

    import json

    meta = json.loads(node.node_metadata)
    assert meta["hostname"] == "vpn1"
    assert meta["services_active"] == 4
    assert meta["services_total"] == 6
    assert meta["antizapret_version"] == "abc123"
    db.commit.assert_called_once()
