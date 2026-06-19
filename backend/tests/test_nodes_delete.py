"""DELETE /api/nodes/{id} — HA group membership guard."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import get_password_hash
from app.models import (
    AlertRule,
    AlertRuleMetric,
    AlertRuleOperator,
    ClientTemplate,
    ConfigTag,
    Node,
    NodeStatus,
    NodeSyncGroup,
    User,
    UserRole,
    UserTrafficStatProtocol,
    VpnConfig,
    VpnType,
)
from app.services.node_sync.groups import serialize_replica_node_ids
from tests.conftest import run_async


@pytest.fixture()
def ha_nodes(api_test_env):
    session = api_test_env["session_factory"]()
    primary = Node(
        name="primary",
        host="10.0.0.1",
        port=9100,
        status=NodeStatus.online,
        node_metadata=json.dumps({"antizapret_version": "v1.0.0"}),
    )
    replica = Node(
        name="replica",
        host="10.0.0.2",
        port=9100,
        status=NodeStatus.online,
        node_metadata=json.dumps({"antizapret_version": "v1.0.0"}),
    )
    standalone = Node(
        name="standalone",
        host="10.0.0.3",
        port=9100,
        status=NodeStatus.online,
    )
    session.add_all([primary, replica, standalone])
    session.commit()

    group = NodeSyncGroup(
        name="HA vpn",
        shared_domain="vpn.example.com",
        primary_node_id=primary.id,
        replica_node_ids=serialize_replica_node_ids([replica.id]),
        sync_mode="auto",
    )
    session.add(group)
    session.commit()

    api_test_env["primary_id"] = primary.id
    api_test_env["replica_id"] = replica.id
    api_test_env["standalone_id"] = standalone.id
    api_test_env["group_id"] = group.id
    session.close()
    yield api_test_env
    session = api_test_env["session_factory"]()
    session.query(NodeSyncGroup).delete()
    session.commit()
    session.close()


def _delete_node(env, node_id: int):
    app = env["app"]
    headers = env["admin_headers"]

    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.delete(f"/api/nodes/{node_id}", headers=headers)

    return run_async(_run())


def test_delete_primary_in_ha_group_returns_409(ha_nodes):
    env = ha_nodes
    response = _delete_node(env, env["primary_id"])
    assert response.status_code == 409, response.text
    assert "primary" in response.json()["detail"]
    assert "HA vpn" in response.json()["detail"]
    assert "расформируйте" in response.json()["detail"]

    session = env["session_factory"]()
    assert session.query(Node).filter(Node.id == env["primary_id"]).first() is not None
    assert session.query(NodeSyncGroup).filter(NodeSyncGroup.id == env["group_id"]).first() is not None
    session.close()


def test_delete_replica_in_ha_group_returns_409(ha_nodes):
    env = ha_nodes
    response = _delete_node(env, env["replica_id"])
    assert response.status_code == 409, response.text
    assert "replica" in response.json()["detail"]
    assert "HA vpn" in response.json()["detail"]

    session = env["session_factory"]()
    assert session.query(Node).filter(Node.id == env["replica_id"]).first() is not None
    assert session.query(NodeSyncGroup).filter(NodeSyncGroup.id == env["group_id"]).first() is not None
    session.close()


def test_delete_remote_node_purges_related_data(api_test_env):
    session = api_test_env["session_factory"]()
    admin = User(
        username="purge-admin",
        password_hash=get_password_hash("secret"),
        role=UserRole.admin,
        is_active=True,
    )
    node = Node(
        name="purge-target",
        host="10.0.0.99",
        port=9100,
        status=NodeStatus.online,
    )
    session.add_all([admin, node])
    session.commit()
    session.refresh(node)

    session.add_all(
        [
            VpnConfig(
                node_id=node.id,
                client_name="client-a",
                vpn_type=VpnType.openvpn,
                owner_id=admin.id,
            ),
            UserTrafficStatProtocol(
                node_id=node.id,
                common_name="client-a",
                protocol_type="openvpn",
                total_received=100,
                total_sent=50,
            ),
        ]
    )
    session.commit()
    node_id = node.id
    session.close()

    response = _delete_node(api_test_env, node_id)
    assert response.status_code == 200, response.text

    session = api_test_env["session_factory"]()
    assert session.query(Node).filter(Node.id == node_id).first() is None
    assert session.query(VpnConfig).filter(VpnConfig.node_id == node_id).count() == 0
    assert (
        session.query(UserTrafficStatProtocol)
        .filter(UserTrafficStatProtocol.node_id == node_id)
        .count()
        == 0
    )
    session.close()


def test_delete_remote_node_purges_tags_templates_and_alert_rules(api_test_env):
    session = api_test_env["session_factory"]()
    admin = User(
        username="purge-tags-admin",
        password_hash=get_password_hash("secret"),
        role=UserRole.admin,
        is_active=True,
    )
    node = Node(
        name="purge-tags-target",
        host="10.0.0.88",
        port=9100,
        status=NodeStatus.online,
    )
    session.add_all([admin, node])
    session.commit()
    session.refresh(node)

    session.add_all(
        [
            ConfigTag(node_id=node.id, name="prod"),
            ClientTemplate(
                node_id=node.id,
                name="custom-tpl",
                vpn_type=VpnType.openvpn,
                is_builtin=False,
            ),
            AlertRule(
                name="node-offline",
                metric=AlertRuleMetric.nodes_offline,
                operator=AlertRuleOperator.gt,
                threshold=0,
                node_id=node.id,
            ),
        ]
    )
    session.commit()
    node_id = node.id
    session.close()

    response = _delete_node(api_test_env, node_id)
    assert response.status_code == 200, response.text

    session = api_test_env["session_factory"]()
    assert session.query(Node).filter(Node.id == node_id).first() is None
    assert session.query(ConfigTag).filter(ConfigTag.node_id == node_id).count() == 0
    assert session.query(ClientTemplate).filter(ClientTemplate.node_id == node_id).count() == 0
    assert session.query(AlertRule).filter(AlertRule.node_id == node_id).count() == 0
    session.close()


def test_delete_node_outside_ha_group_succeeds(ha_nodes):
    env = ha_nodes
    standalone_id = env["standalone_id"]
    response = _delete_node(env, standalone_id)
    assert response.status_code == 200, response.text
    assert "standalone" in response.json()["message"]

    session = env["session_factory"]()
    assert session.query(Node).filter(Node.id == standalone_id).first() is None
    session.close()
