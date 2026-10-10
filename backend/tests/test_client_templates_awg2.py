"""Client templates create AmneziaWG 2.0 clients and their traffic limit through AWG2, not WireGuard."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ClientTemplate, Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.services import client_templates

_FIVE_GB = 5 * 1024**3


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _node(db) -> Node:
    node = Node(
        name="primary",
        host="127.0.0.1",
        port=9100,
        api_key_hash="hash",
        api_key_encrypted="enc",
        status=NodeStatus.online,
        is_local=True,
        node_kind="vpn",
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _owner(db) -> User:
    user = User(username="admin", password_hash="x", role=UserRole.admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _awg2_template(db, node: Node) -> ClientTemplate:
    template = ClientTemplate(
        node_id=node.id,
        name="AWG2 5 GB",
        vpn_type=VpnType.amneziawg2,
        traffic_limit_value=5,
        traffic_limit_unit="gb",
        traffic_limit_period_days=30,
        is_builtin=False,
        sort_order=0,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def _apply(db, node, owner, template, adapter, svc, tmp_path, client_name="olga"):
    actor = SimpleNamespace(id=owner.id, username="admin", role=UserRole.admin)
    with (
        patch.object(client_templates, "require_vpn_type"),
        patch.object(client_templates, "get_active_node", return_value=node),
        patch.object(client_templates, "get_active_adapter", return_value=adapter),
        patch.object(client_templates, "get_node_antizapret_path", return_value=tmp_path),
        patch.object(client_templates, "AccessPolicyService", return_value=svc),
        patch.object(client_templates, "refresh_config_cert_expiry"),
        patch.object(client_templates, "purge_traffic_history_for_reused_name"),
        patch.object(client_templates, "maybe_replicate_create"),
        patch.object(client_templates, "maybe_replicate_policy_op") as replicate_policy,
    ):
        config = client_templates.apply_template(
            db,
            template,
            client_name=client_name,
            owner_id=owner.id,
            actor=actor,
            feature_service=SimpleNamespace(),
        )
    return config, replicate_policy


def test_awg2_template_creates_awg2_client_with_awg2_limit(db, tmp_path):
    node, owner = _node(db), _owner(db)
    template = _awg2_template(db, node)
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {"installed": True}
    svc = MagicMock()

    config, replicate_policy = _apply(db, node, owner, template, adapter, svc, tmp_path)

    assert config.vpn_type == VpnType.amneziawg2
    assert config.cert_expire_days is None
    adapter.awg2_add_client.assert_called_once_with("olga")
    adapter.add_wireguard_client.assert_not_called()
    svc.awg2_set_traffic_limit.assert_called_once_with("olga", _FIVE_GB, period_days=30, actor="admin")
    svc.wg_set_traffic_limit.assert_not_called()
    replicate_policy.assert_called_once_with(
        db,
        node_id=node.id,
        client_name="olga",
        vpn_type=VpnType.amneziawg2,
        op="set_traffic_limit",
        actor="admin",
        limit_bytes=_FIVE_GB,
        period_days=30,
    )


def test_awg2_template_without_awg2_layer_is_409(db, tmp_path):
    node, owner = _node(db), _owner(db)
    template = _awg2_template(db, node)
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {"installed": False}

    with pytest.raises(HTTPException) as exc:
        _apply(db, node, owner, template, adapter, MagicMock(), tmp_path)

    assert exc.value.status_code == 409
    assert exc.value.detail["message"] == "AZ-AWG2 не установлен на узле"
    adapter.awg2_add_client.assert_not_called()
    assert db.query(VpnConfig).count() == 0


def test_template_rejects_reserved_prefix(db, tmp_path):
    node, owner = _node(db), _owner(db)
    template = _awg2_template(db, node)
    adapter = MagicMock()

    with pytest.raises(ValueError, match="не может начинаться"):
        _apply(db, node, owner, template, adapter, MagicMock(), tmp_path, client_name="vpn-olga")

    adapter.get_awg2_health.assert_not_called()
    adapter.awg2_add_client.assert_not_called()
