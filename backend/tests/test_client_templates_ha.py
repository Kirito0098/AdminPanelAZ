"""HA auto-sync for client template apply."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.models import (
    AppSetting,
    ClientTemplate,
    Node,
    NodeStatus,
    NodeSyncGroup,
    OpenVpnAccessPolicy,
    User,
    VpnConfig,
    VpnType,
    WgAccessPolicy,
)
from app.services.client_templates import apply_template
from app.services.feature_guards import get_feature_service
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


def _ha_group(session, *, primary_node_id: int, replica_node_id: int, sync_mode: str = "auto") -> NodeSyncGroup:
    group = NodeSyncGroup(
        name="HA templates",
        shared_domain="vpn.example.com",
        primary_node_id=primary_node_id,
        replica_node_ids=serialize_replica_node_ids([replica_node_id]),
        sync_mode=sync_mode,
    )
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


@contextmanager
def _ip_patches():
    with patch("app.main.ip_restriction_service.should_hard_deny", return_value=False), patch(
        "app.main.ip_restriction_service.get_settings",
        return_value={"ip_restriction_enabled": False},
    ), patch("app.main.ip_restriction_service.is_ip_allowed", return_value=True):
        yield


@pytest.fixture()
def ha_template_env(api_test_env):
    session_factory = api_test_env["session_factory"]
    db = session_factory()
    primary = db.query(Node).filter_by(is_local=True).one()
    replica = Node(name="replica-tpl", host="10.0.0.50", port=9100, status=NodeStatus.online)
    admin = db.query(User).filter(User.username == "api_admin").one()
    db.add(replica)
    db.commit()
    db.refresh(replica)

    group = _ha_group(db, primary_node_id=primary.id, replica_node_id=replica.id)
    template = ClientTemplate(
        node_id=primary.id,
        name="HA WG limit",
        vpn_type=VpnType.wireguard,
        traffic_limit_value=10,
        traffic_limit_unit="GB",
        traffic_limit_period_days=30,
        description_template="from template",
        sort_order=1,
        is_builtin=False,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    primary_id = primary.id
    replica_id = replica.id
    template_id = template.id
    admin_id = admin.id
    group_id = group.id
    db.close()
    _set_active_node(session_factory, primary_id)

    yield {
        **api_test_env,
        "primary_id": primary_id,
        "replica_id": replica_id,
        "template_id": template_id,
        "admin_id": admin_id,
        "group_id": group_id,
    }


def test_apply_template_replicates_client_and_policy_in_auto_ha(ha_template_env):
    mock_adapter = ha_template_env["mock_adapter"]
    session_factory = ha_template_env["session_factory"]

    with patch("app.services.node_sync.replicate.get_adapter_for_node", return_value=mock_adapter), patch(
        "app.services.node_sync.policy_sync.get_adapter_for_node",
        return_value=mock_adapter,
    ), patch(
        "app.services.access_policy.block_client_runtime",
        return_value=None,
    ), patch(
        "app.services.access_policy.unblock_client_runtime",
        return_value=None,
    ):
        db = session_factory()
        admin = db.query(User).filter(User.id == ha_template_env["admin_id"]).one()
        template = db.query(ClientTemplate).filter(ClientTemplate.id == ha_template_env["template_id"]).one()
        config = apply_template(
            db,
            template,
            client_name="tpl-ha-client",
            owner_id=admin.id,
            actor=admin,
            feature_service=get_feature_service(),
        )
        primary_config_id = config.id
        db.close()

    verify = session_factory()
    try:
        shadow = (
            verify.query(VpnConfig)
            .filter(
                VpnConfig.node_id == ha_template_env["replica_id"],
                VpnConfig.client_name == "tpl-ha-client",
            )
            .one()
        )
        assert shadow.ha_primary_config_id == primary_config_id
        assert shadow.description == "from template"

        primary_policy = (
            verify.query(WgAccessPolicy)
            .filter(
                WgAccessPolicy.node_id == ha_template_env["primary_id"],
                WgAccessPolicy.client_name == "tpl-ha-client",
            )
            .one()
        )
        replica_policy = (
            verify.query(WgAccessPolicy)
            .filter(
                WgAccessPolicy.node_id == ha_template_env["replica_id"],
                WgAccessPolicy.client_name == "tpl-ha-client",
            )
            .one()
        )
        assert primary_policy.traffic_limit_bytes == replica_policy.traffic_limit_bytes
        assert primary_policy.traffic_limit_period_days == 30
    finally:
        verify.close()

    mock_adapter.add_wireguard_client.assert_called()
    assert mock_adapter.add_wireguard_client.call_count >= 2


def test_apply_template_api_replicates_in_auto_ha(ha_template_env):
    client = TestClient(ha_template_env["app"])
    headers = ha_template_env["admin_headers"]
    mock_adapter = ha_template_env["mock_adapter"]

    with _ip_patches(), patch("app.services.node_sync.replicate.get_adapter_for_node", return_value=mock_adapter), patch(
        "app.services.node_sync.policy_sync.get_adapter_for_node",
        return_value=mock_adapter,
    ), patch(
        "app.services.access_policy.block_client_runtime",
        return_value=None,
    ), patch(
        "app.services.access_policy.unblock_client_runtime",
        return_value=None,
    ):
        resp = client.post(
            f"/api/client-templates/{ha_template_env['template_id']}/apply",
            headers=headers,
            json={"client_name": "api-tpl-client"},
        )

    assert resp.status_code == 201
    assert resp.json()["client_name"] == "api-tpl-client"

    verify = ha_template_env["session_factory"]()
    try:
        assert (
            verify.query(VpnConfig)
            .filter(
                VpnConfig.node_id == ha_template_env["replica_id"],
                VpnConfig.client_name == "api-tpl-client",
            )
            .count()
            == 1
        )
        replica_policy = (
            verify.query(WgAccessPolicy)
            .filter(
                WgAccessPolicy.node_id == ha_template_env["replica_id"],
                WgAccessPolicy.client_name == "api-tpl-client",
            )
            .one()
        )
        assert replica_policy.traffic_limit_bytes is not None
        assert replica_policy.traffic_limit_period_days == 30
    finally:
        verify.close()


def test_apply_template_manual_sync_links_primary_without_replica(ha_template_env):
    session_factory = ha_template_env["session_factory"]
    db = session_factory()
    group = db.query(NodeSyncGroup).filter(NodeSyncGroup.id == ha_template_env["group_id"]).one()
    group.sync_mode = "manual_full"
    db.commit()
    admin = db.query(User).filter(User.id == ha_template_env["admin_id"]).one()
    template = db.query(ClientTemplate).filter(ClientTemplate.id == ha_template_env["template_id"]).one()
    db.close()

    mock_adapter = ha_template_env["mock_adapter"]
    with patch("app.services.node_sync.replicate.get_adapter_for_node", return_value=mock_adapter):
        db = session_factory()
        config = apply_template(
            db,
            template,
            client_name="manual-tpl-client",
            owner_id=admin.id,
            actor=admin,
            feature_service=get_feature_service(),
        )
        db.close()

    verify = session_factory()
    try:
        primary_config = (
            verify.query(VpnConfig)
            .filter(
                VpnConfig.node_id == ha_template_env["primary_id"],
                VpnConfig.client_name == "manual-tpl-client",
            )
            .one()
        )
        assert primary_config.sync_group_id == ha_template_env["group_id"]
        assert (
            verify.query(VpnConfig)
            .filter(VpnConfig.ha_primary_config_id == primary_config.id)
            .count()
            == 0
        )
    finally:
        verify.close()

    mock_adapter.add_wireguard_client.assert_called_once()


def test_apply_template_without_traffic_limit_replicates_client_only(ha_template_env):
    session_factory = ha_template_env["session_factory"]
    db = session_factory()
    template = ClientTemplate(
        node_id=ha_template_env["primary_id"],
        name="HA OVPN plain",
        vpn_type=VpnType.openvpn,
        cert_expire_days=365,
        sort_order=2,
        is_builtin=False,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    template_id = template.id
    admin = db.query(User).filter(User.id == ha_template_env["admin_id"]).one()
    db.close()

    mock_adapter = ha_template_env["mock_adapter"]
    with patch("app.services.node_sync.replicate.get_adapter_for_node", return_value=mock_adapter):
        db = session_factory()
        apply_template(
            db,
            db.query(ClientTemplate).filter(ClientTemplate.id == template_id).one(),
            client_name="tpl-no-limit",
            owner_id=admin.id,
            actor=admin,
            feature_service=get_feature_service(),
        )
        db.close()

    verify = session_factory()
    try:
        assert (
            verify.query(VpnConfig)
            .filter(
                VpnConfig.node_id == ha_template_env["replica_id"],
                VpnConfig.client_name == "tpl-no-limit",
            )
            .count()
            == 1
        )
        assert (
            verify.query(OpenVpnAccessPolicy)
            .filter(
                OpenVpnAccessPolicy.node_id == ha_template_env["replica_id"],
                OpenVpnAccessPolicy.client_name == "tpl-no-limit",
            )
            .count()
            == 0
        )
    finally:
        verify.close()
