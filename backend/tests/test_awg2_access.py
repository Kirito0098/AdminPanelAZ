from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AmneziaWg2AccessPolicy, Node, NodeStatus
from app.services.access_policy import AccessPolicyService


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


def _make_node(db) -> Node:
    node = Node(
        name="node-1",
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

    awg2_row = (
        db.query(AmneziaWg2AccessPolicy)
        .filter_by(node_id=node.id, client_name="same-client")
        .first()
    )

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

    row = (
        db.query(AmneziaWg2AccessPolicy)
        .filter_by(node_id=node.id, client_name="locked")
        .first()
    )

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
