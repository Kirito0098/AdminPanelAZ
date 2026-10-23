from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AmneziaWg2AccessPolicy, Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.services.access_policy import AccessPolicyService
from app.services.policy_import import copy_access_policies_from_node
from app.services.node_sync import policy_sync


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _make_node(db, *, name: str = "node-1") -> Node:
    node = Node(
        name=name,
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _make_owner(db) -> User:
    user = User(username="owner", password_hash="hash", role=UserRole.admin, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_service(db, node_id: int) -> AccessPolicyService:
    return AccessPolicyService(db, antizapret_path=Path("/tmp"), node_id=node_id, node_name="node-1")


def test_awg2_temp_block_calls_awg2_runtime_not_wg(db):
    node = _make_node(db)
    service = _make_service(db, node.id)
    with (
        patch("app.services.access_policy.block_client_runtime") as wg_block,
        patch("app.services.access_policy.unblock_client_runtime") as wg_unblock,
        patch("app.services.access_policy.awg2_block_client_runtime", return_value={"success": True}) as awg2_block,
    ):
        state = service.awg2_temp_block("Ivan", 3, actor="admin")

    assert state["is_blocked"] is True
    assert state["block_mode"] == "temp"
    assert state["block_duration_days"] == 3
    awg2_block.assert_called_once_with("ivan")
    wg_block.assert_not_called()
    wg_unblock.assert_not_called()


def test_policy_isolation_same_name_wg_unaffected(db):
    node = _make_node(db)
    service = _make_service(db, node.id)
    with (
        patch("app.services.access_policy.block_client_runtime", return_value={"success": True}) as wg_block,
        patch("app.services.access_policy.unblock_client_runtime", return_value={"success": True}) as wg_unblock,
        patch("app.services.access_policy.awg2_block_client_runtime", return_value={"success": True}) as awg2_block,
        patch("app.services.access_policy.awg2_unblock_client_runtime", return_value={"success": True}) as awg2_unblock,
    ):
        wg_state = service.wg_permanent_block("same-client", actor="admin")
        awg2_state = service.awg2_temp_block("same-client", 2, actor="admin")

    awg2_row = db.query(AmneziaWg2AccessPolicy).filter_by(node_id=node.id, client_name="same-client").first()

    assert wg_state["is_blocked"] is True
    assert wg_state["block_mode"] == "permanent"
    assert awg2_state["is_blocked"] is True
    assert awg2_state["block_mode"] == "temp"
    assert awg2_row is not None
    assert awg2_row.is_temp_blocked is True
    assert awg2_row.is_permanent_blocked is False
    wg_block.assert_called_once_with("same-client")
    wg_unblock.assert_not_called()
    awg2_block.assert_called_once_with("same-client")
    awg2_unblock.assert_not_called()


def test_awg2_unblock_clears_flags_and_restores_runtime(db):
    node = _make_node(db)
    service = _make_service(db, node.id)
    with (
        patch("app.services.access_policy.awg2_block_client_runtime", return_value={"success": True}) as awg2_block,
        patch("app.services.access_policy.awg2_unblock_client_runtime", return_value={"success": True}) as awg2_unblock,
    ):
        service.awg2_permanent_block("locked", actor="admin")
        state = service.awg2_unblock("locked", actor="admin")

    row = db.query(AmneziaWg2AccessPolicy).filter_by(node_id=node.id, client_name="locked").first()

    assert state["is_blocked"] is False
    assert state["block_mode"] == "none"
    assert row is not None
    assert row.is_temp_blocked is False
    assert row.is_permanent_blocked is False
    assert row.block_reason is None
    assert row.block_started_at is None
    assert row.block_days is None
    assert row.block_until is None
    awg2_block.assert_called_once_with("locked")
    awg2_unblock.assert_called_once_with("locked")


def test_replicate_awg2_block_temp_invokes_replica_awg2_runtime(db):
    owner = _make_owner(db)
    primary = _make_node(db, name="primary")
    replica = _make_node(db, name="replica")
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="Ivan",
        vpn_type=VpnType.amneziawg2,
        owner_id=owner.id,
    )
    db.add(primary_config)
    db.commit()
    db.refresh(primary_config)
    adapter = MagicMock()
    group = SimpleNamespace(primary_node_id=primary.id, sync_mode="auto")
    shadow = SimpleNamespace(node_id=replica.id, id=77)

    with (
        patch.object(policy_sync, "get_replica_nodes", return_value=[replica]),
        patch.object(policy_sync, "get_shadow_configs", return_value=[shadow]),
        patch.object(policy_sync, "get_adapter_for_node", return_value=adapter),
        patch.object(policy_sync, "finalize_replicate_outcome"),
    ):
        result = policy_sync.replicate_policy_op(
            db,
            group,
            primary_config,
            "block_temp",
            days=3,
            actor="admin",
        )

    row = db.query(AmneziaWg2AccessPolicy).filter_by(node_id=replica.id, client_name="ivan").first()
    assert result == {"applied": [{"node_id": replica.id, "config_id": 77}], "errors": [], "skipped": False}
    assert row is not None
    assert row.is_temp_blocked is True
    assert row.block_days == 3
    adapter.block_awg2_client_runtime.assert_called_once_with("ivan")


def test_copy_access_policies_from_node_copies_awg2_rows(db):
    source = _make_node(db, name="source")
    target = _make_node(db, name="target")
    db.add(
        AmneziaWg2AccessPolicy(
            node_id=source.id,
            client_name="ivan",
            is_temp_blocked=True,
            block_reason="manual_temp",
            block_days=5,
            updated_by="admin",
        )
    )
    db.commit()

    copied = copy_access_policies_from_node(db, source, target)

    row = db.query(AmneziaWg2AccessPolicy).filter_by(node_id=target.id, client_name="ivan").first()
    assert copied == 1
    assert row is not None
    assert row.is_temp_blocked is True
    assert row.block_reason == "manual_temp"
    assert row.block_days == 5
    assert row.updated_by == "admin"


def test_awg2_temp_block_uses_adapter_runtime_when_present(db):
    node = _make_node(db)
    adapter = MagicMock()
    service = AccessPolicyService(
        db,
        antizapret_path=Path("/tmp"),
        node_id=node.id,
        node_name="node-1",
        adapter=adapter,
    )
    with (
        patch("app.services.access_policy.awg2_block_client_runtime") as local_block,
        patch("app.services.access_policy.awg2_unblock_client_runtime") as local_unblock,
    ):
        state = service.awg2_temp_block("Ivan", 3, actor="admin")

    assert state["is_blocked"] is True
    adapter.block_awg2_client_runtime.assert_called_once_with("ivan")
    local_block.assert_not_called()
    local_unblock.assert_not_called()
