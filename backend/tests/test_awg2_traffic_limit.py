from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AmneziaWg2AccessPolicy, Node, NodeStatus
from app.services.access_policy import AccessPolicyService
from app.services.traffic_limit import AMNEZIAWG2_PROTOCOL


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


def _make_service(db, node_id: int) -> AccessPolicyService:
    return AccessPolicyService(db, antizapret_path=Path("/tmp"), node_id=node_id, node_name="node-1")


def test_amneziawg2_protocol_constant():
    assert AMNEZIAWG2_PROTOCOL == frozenset({"amneziawg2"})


def test_awg2_state_traffic_limit_exceeded(db, monkeypatch):
    node = _make_node(db)
    service = _make_service(db, node.id)
    row = AmneziaWg2AccessPolicy(
        node_id=node.id,
        client_name="ivan",
        traffic_limit_bytes=100,
        traffic_limit_period_days=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    monkeypatch.setattr(service, "_consumed_bytes", lambda *a, **k: 200)

    state = service._awg2_state(row)

    assert state["is_blocked"] is True
    assert state["block_mode"] == "traffic_limit"
    assert state["traffic_limit_exceeded"] is True
    assert state["traffic_limit_bytes"] == 100
    assert state["traffic_consumed_bytes"] == 200


def test_awg2_clear_traffic_limit_unblocks(db, monkeypatch):
    node = _make_node(db)
    service = _make_service(db, node.id)

    with (
        patch("app.services.access_policy.awg2_block_client_runtime", return_value={"success": True}) as awg2_block,
        patch("app.services.access_policy.awg2_unblock_client_runtime", return_value={"success": True}) as awg2_unblock,
    ):
        monkeypatch.setattr(service, "_consumed_bytes", lambda *a, **k: 200)
        exceeded = service.awg2_set_traffic_limit("ivan", 100, actor="admin")
        assert exceeded["block_mode"] == "traffic_limit"
        assert exceeded["is_blocked"] is True

        cleared = service.awg2_clear_traffic_limit("ivan", actor="admin")

    assert cleared["is_blocked"] is False
    assert cleared["block_mode"] == "none"
    assert cleared["traffic_limit_exceeded"] is False
    assert cleared["traffic_limit_bytes"] is None

    row = (
        db.query(AmneziaWg2AccessPolicy)
        .filter_by(node_id=node.id, client_name="ivan")
        .first()
    )
    assert row is not None
    assert row.traffic_limit_bytes is None
    assert row.traffic_limit_period_days is None
    assert row.block_reason is None
    awg2_block.assert_called()
    awg2_unblock.assert_called()


def test_awg2_perm_block_priority_over_traffic(db, monkeypatch):
    node = _make_node(db)
    service = _make_service(db, node.id)
    row = AmneziaWg2AccessPolicy(
        node_id=node.id,
        client_name="ivan",
        is_permanent_blocked=True,
        traffic_limit_bytes=100,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    monkeypatch.setattr(service, "_consumed_bytes", lambda *a, **k: 200)

    state = service._awg2_state(row)

    assert state["is_blocked"] is True
    assert state["block_mode"] == "permanent"
    assert state["traffic_limit_exceeded"] is True


def test_get_awg2_policy_includes_traffic_fields_without_row(db, monkeypatch):
    node = _make_node(db)
    service = _make_service(db, node.id)
    monkeypatch.setattr(service, "_consumed_bytes", lambda *a, **k: 42)

    state = service.get_awg2_policy("missing-client")

    assert state["is_blocked"] is False
    assert state["block_mode"] == "none"
    assert state["traffic_consumed_bytes"] == 42
    assert state["traffic_limit_bytes"] is None
    assert "traffic_consumed_human" in state


def test_reconcile_all_traffic_limits_walks_awg2(db, monkeypatch):
    node = _make_node(db)
    service = _make_service(db, node.id)
    db.add(
        AmneziaWg2AccessPolicy(
            node_id=node.id,
            client_name="ivan",
            traffic_limit_bytes=100,
        )
    )
    db.commit()

    calls: list[str] = []

    def _fake_reconcile(client_name, **kwargs):
        calls.append(client_name)

    monkeypatch.setattr(service, "reconcile_awg2", _fake_reconcile)
    monkeypatch.setattr(service, "reconcile_wg", lambda *a, **k: None)
    monkeypatch.setattr(service, "reconcile_openvpn", lambda *a, **k: None)

    result = service.reconcile_all_traffic_limits(node_id=node.id)

    assert "ivan" in calls
    assert result["traffic_limit_reconcile"] == "ok"
    assert result["clients_total"] >= 1
