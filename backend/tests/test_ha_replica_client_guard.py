"""HA replica guard: block client mutations on replica nodes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import AppSetting, Node, NodeStatus, NodeSyncGroup, User, VpnConfig, VpnType
from app.services.node_sync.groups import serialize_replica_node_ids


def _set_active_node(session_factory, node_id: int) -> None:
    db = session_factory()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "active_node_id").first()
        if row:
            row.value = str(node_id)
        else:
            db.add(AppSetting(key="active_node_id", value=str(node_id)))
        db.commit()
    finally:
        db.close()


def _ha_group(session_factory, *, primary_node_id: int, replica_node_id: int) -> NodeSyncGroup:
    db = session_factory()
    try:
        group = NodeSyncGroup(
            name="HA test",
            shared_domain="vpn.example.com",
            primary_node_id=primary_node_id,
            replica_node_ids=serialize_replica_node_ids([replica_node_id]),
            sync_mode="auto",
        )
        db.add(group)
        db.commit()
        db.refresh(group)
        return group
    finally:
        db.close()


def test_active_node_includes_ha_context_for_replica(api_test_env):
    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]
    session_factory = api_test_env["session_factory"]

    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-1", host="10.0.0.2", port=9100, status=NodeStatus.online)
    db.add(replica)
    db.commit()
    db.refresh(replica)
    replica_id = replica.id
    primary_id = primary.id
    db.close()

    _ha_group(session_factory, primary_node_id=primary_id, replica_node_id=replica_id)
    _set_active_node(session_factory, replica_id)

    resp = client.get("/api/nodes/active", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ha"]["role"] == "replica"
    assert body["ha"]["primary_node_id"] == primary_id
    assert body["ha"]["group_name"] == "HA test"


def test_create_config_blocked_on_ha_replica(api_test_env):
    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]
    session_factory = api_test_env["session_factory"]

    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-2", host="10.0.0.3", port=9100, status=NodeStatus.online)
    db.add(replica)
    db.commit()
    db.refresh(replica)
    replica_id = replica.id
    primary_id = primary.id
    db.close()

    _ha_group(session_factory, primary_node_id=primary_id, replica_node_id=replica_id)
    _set_active_node(session_factory, replica_id)

    resp = client.post(
        "/api/configs",
        headers=headers,
        json={"client_name": "replica-only", "vpn_type": "openvpn", "cert_expire_days": 365},
    )
    assert resp.status_code == 403
    assert "replica" in resp.json()["detail"].lower()
    assert "primary" in resp.json()["detail"].lower()


def test_delete_config_blocked_on_ha_replica(api_test_env):
    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]
    session_factory = api_test_env["session_factory"]

    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-3", host="10.0.0.4", port=9100, status=NodeStatus.online)
    admin = db.query(User).filter(User.username == "api_admin").first()
    db.add(replica)
    db.commit()
    db.refresh(replica)
    cfg = VpnConfig(
        node_id=primary.id,
        client_name="primary-client",
        vpn_type=VpnType.openvpn,
        owner_id=admin.id,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    config_id = cfg.id
    replica_id = replica.id
    primary_id = primary.id
    db.close()

    _ha_group(session_factory, primary_node_id=primary_id, replica_node_id=replica_id)
    _set_active_node(session_factory, replica_id)

    resp = client.delete(f"/api/configs/{config_id}", headers=headers)
    assert resp.status_code == 403


def test_update_description_blocked_on_ha_replica(api_test_env):
    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]
    session_factory = api_test_env["session_factory"]

    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-4", host="10.0.0.5", port=9100, status=NodeStatus.online)
    admin = db.query(User).filter(User.username == "api_admin").first()
    db.add(replica)
    db.commit()
    db.refresh(replica)
    cfg = VpnConfig(
        node_id=primary.id,
        client_name="meta-client",
        vpn_type=VpnType.openvpn,
        owner_id=admin.id,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    config_id = cfg.id
    replica_id = replica.id
    primary_id = primary.id
    db.close()

    _ha_group(session_factory, primary_node_id=primary_id, replica_node_id=replica_id)
    _set_active_node(session_factory, replica_id)

    resp = client.patch(
        f"/api/configs/{config_id}",
        headers=headers,
        json={"description": "updated from replica view"},
    )
    assert resp.status_code == 403
    assert "replica" in resp.json()["detail"].lower()
