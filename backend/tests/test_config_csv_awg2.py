"""CSV export and import keep AmneziaWG 2.0 clients and their AWG2 access policies."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    AmneziaWg2AccessPolicy,
    Node,
    NodeStatus,
    User,
    UserRole,
    VpnConfig,
    VpnType,
    WgAccessPolicy,
)
from app.services import config_csv_ops

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


def _export_rows(db, node: Node) -> list[dict[str, str]]:
    content = "".join(config_csv_ops.iter_config_export_csv(db, node_id=node.id))
    return config_csv_ops.parse_import_csv(content.encode("utf-8"))


def _import(db, node: Node, owner: User, adapter: MagicMock, svc: MagicMock, tmp_path, row: dict[str, str]) -> dict:
    with (
        patch.object(config_csv_ops, "require_vpn_type"),
        patch.object(config_csv_ops, "get_feature_service", return_value=SimpleNamespace()),
        patch.object(config_csv_ops, "get_active_adapter", return_value=adapter),
        patch.object(config_csv_ops, "get_node_antizapret_path", return_value=tmp_path),
        patch.object(config_csv_ops, "AccessPolicyService", return_value=svc),
        patch.object(config_csv_ops, "refresh_config_cert_expiry"),
        patch.object(config_csv_ops, "purge_traffic_history_for_reused_name"),
        patch.object(config_csv_ops, "maybe_replicate_create"),
        patch.object(config_csv_ops, "maybe_replicate_policy_op"),
        patch("app.services.user_subscription.apply_owner_access_until_to_config", return_value={}),
        patch("app.services.user_subscription.replicate_inherited_access_until"),
    ):
        return config_csv_ops._import_single_row(
            db,
            row={"_line": "2", **row},
            node_id=node.id,
            default_owner_id=owner.id,
            owner_by_username={"admin": owner.id},
            actor_username="admin",
        )


def _awg2_adapter(installed: bool = True) -> MagicMock:
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {"installed": installed}
    return adapter


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("amneziawg2", VpnType.amneziawg2),
        ("AWG2", VpnType.amneziawg2),
        ("awg", VpnType.wireguard),
        ("amneziawg", VpnType.wireguard),
    ],
)
def test_vpn_type_aliases(raw, expected):
    assert config_csv_ops._normalize_vpn_type(raw) == expected


def test_export_reads_the_awg2_policy(db):
    node, owner = _node(db), _owner(db)
    db.add(VpnConfig(node_id=node.id, client_name="Olga", vpn_type=VpnType.amneziawg2, owner_id=owner.id))
    db.add(
        AmneziaWg2AccessPolicy(
            node_id=node.id,
            client_name="olga",
            traffic_limit_bytes=_FIVE_GB,
            traffic_limit_period_days=30,
            is_permanent_blocked=True,
        )
    )
    db.add(WgAccessPolicy(node_id=node.id, client_name="olga", is_temp_blocked=True, block_days=3))
    db.commit()

    [row] = _export_rows(db, node)

    assert row["vpn_type"] == "amneziawg2"
    assert row["traffic_limit_bytes"] == str(_FIVE_GB)
    assert row["traffic_limit_days"] == "30"
    assert row["block_mode"] == "permanent"


def test_exported_awg2_row_imports_back(db, tmp_path):
    node, owner = _node(db), _owner(db)
    config = VpnConfig(
        node_id=node.id, client_name="olga", vpn_type=VpnType.amneziawg2, owner_id=owner.id, description="phone"
    )
    db.add(config)
    db.add(
        AmneziaWg2AccessPolicy(
            node_id=node.id,
            client_name="olga",
            traffic_limit_bytes=_FIVE_GB,
            traffic_limit_period_days=30,
            is_temp_blocked=True,
            block_days=3,
        )
    )
    db.commit()
    [row] = _export_rows(db, node)
    db.delete(config)
    db.query(AmneziaWg2AccessPolicy).delete()
    db.commit()
    adapter, svc = _awg2_adapter(), MagicMock()

    result = _import(db, node, owner, adapter, svc, tmp_path, row)

    assert result["ok"] is True, result
    assert result["vpn_type"] == "amneziawg2"
    adapter.awg2_add_client.assert_called_once_with("olga")
    adapter.add_wireguard_client.assert_not_called()
    created = db.query(VpnConfig).one()
    assert (created.vpn_type, created.description, created.cert_expire_days) == (VpnType.amneziawg2, "phone", None)
    svc.awg2_set_traffic_limit.assert_called_once_with("olga", _FIVE_GB, period_days=30, actor="admin")
    svc.awg2_temp_block.assert_called_once_with("olga", 3, actor="admin")
    svc.wg_set_traffic_limit.assert_not_called()
    svc.wg_temp_block.assert_not_called()


def test_awg2_row_without_awg2_layer_is_rejected(db, tmp_path):
    node, owner = _node(db), _owner(db)
    adapter = _awg2_adapter(installed=False)

    result = _import(db, node, owner, adapter, MagicMock(), tmp_path, {"client_name": "olga", "vpn_type": "amneziawg2"})

    assert result == {"line": "2", "client_name": "olga", "ok": False, "error": "AZ-AWG2 не установлен на узле"}
    adapter.awg2_add_client.assert_not_called()
    assert db.query(VpnConfig).count() == 0


def test_awg2_row_follows_the_name_rules(db, tmp_path):
    node, owner = _node(db), _owner(db)
    adapter = _awg2_adapter()

    result = _import(db, node, owner, adapter, MagicMock(), tmp_path, {"client_name": "vpn-olga", "vpn_type": "amneziawg2"})

    assert result["ok"] is False
    assert "не может начинаться" in result["error"]
    adapter.get_awg2_health.assert_not_called()
    adapter.awg2_add_client.assert_not_called()
