"""Traffic-limit block notifications: dedup state lives in the DB (survives restarts) and covers AWG2."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    AmneziaWg2AccessPolicy,
    Node,
    NodeStatus,
    OpenVpnAccessPolicy,
    TrafficLimitNotifyState,
    WgAccessPolicy,
)
from app.services import traffic_limit_notify as notify_module
from app.services.admin_notify import _client_detail_lines
from app.services.traffic_limit_notify import TrafficLimitNotifyService

LIMIT = 100 * 1024**3


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def node(db) -> Node:
    row = Node(name="vpn-a", host="10.0.0.1", status=NodeStatus.online, node_metadata="{}")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class RecordingNotify:
    def __init__(self) -> None:
        self.blocks: list[tuple[str, str]] = []
        self.unblocks: list[tuple[str, str]] = []

    def send_traffic_limit_block(self, _db, *, target_name, target_type, details=None, node_id=None, node_name=None):
        self.blocks.append((target_type, target_name))

    def send_traffic_limit_unblock(self, _db, *, target_name, target_type, details=None, node_id=None, node_name=None):
        self.unblocks.append((target_type, target_name))


class FakePolicies:
    def __init__(self, states: dict[tuple[str, str], dict]) -> None:
        self.states = states

    def get_openvpn_policy(self, name: str) -> dict:
        return self.states[("openvpn", name)]

    def get_wg_policy(self, name: str) -> dict:
        return self.states[("wg", name)]

    def get_awg2_policy(self, name: str) -> dict:
        return self.states[("awg2", name)]


def _blocked(period_days: int | None = None) -> dict:
    return {
        "traffic_limit_bytes": LIMIT,
        "traffic_limit_period_days": period_days,
        "traffic_limit_exceeded": True,
        "block_mode": "traffic_limit",
        "traffic_consumed_bytes": LIMIT + 1,
    }


def _unblocked(period_days: int | None = None) -> dict:
    return {
        "traffic_limit_bytes": LIMIT,
        "traffic_limit_period_days": period_days,
        "traffic_limit_exceeded": False,
        "block_mode": "none",
        "traffic_consumed_bytes": 0,
    }


def _run(db, node, policies: FakePolicies) -> RecordingNotify:
    notify = RecordingNotify()
    TrafficLimitNotifyService(admin_notify=notify).process_node(db, node, policies)
    return notify


def test_block_is_not_announced_again_after_restart(db, node):
    db.add(WgAccessPolicy(node_id=node.id, client_name="alice", traffic_limit_bytes=LIMIT))
    db.commit()
    policies = FakePolicies({("wg", "alice"): _blocked()})

    assert _run(db, node, policies).blocks == [("wireguard", "alice")]
    assert _run(db, node, policies).blocks == []


def test_awg2_block_is_announced(db, node):
    db.add(AmneziaWg2AccessPolicy(node_id=node.id, client_name="bob", traffic_limit_bytes=LIMIT))
    db.commit()

    notify = _run(db, node, FakePolicies({("awg2", "bob"): _blocked()}))

    assert notify.blocks == [("amneziawg2", "bob")]


def test_openvpn_name_keeps_its_case(db, node):
    db.add(OpenVpnAccessPolicy(node_id=node.id, client_name="Carol", traffic_limit_bytes=LIMIT))
    db.commit()

    notify = _run(db, node, FakePolicies({("openvpn", "Carol"): _blocked()}))

    assert notify.blocks == [("openvpn", "Carol")]


def test_unblock_in_new_period_is_announced_after_restart(db, node, monkeypatch):
    periods = iter([datetime(2026, 10, 1), datetime(2026, 11, 1)])
    monkeypatch.setattr(notify_module, "get_traffic_limit_period_start", lambda _days: next(periods))
    db.add(
        WgAccessPolicy(
            node_id=node.id,
            client_name="dave",
            traffic_limit_bytes=LIMIT,
            traffic_limit_period_days=30,
        )
    )
    db.commit()

    first = _run(db, node, FakePolicies({("wg", "dave"): _blocked(30)}))
    second = _run(db, node, FakePolicies({("wg", "dave"): _unblocked(30)}))

    assert first.blocks == [("wireguard", "dave")]
    assert second.unblocks == [("wireguard", "dave")]


def test_state_of_removed_limit_is_dropped(db, node):
    policy = WgAccessPolicy(node_id=node.id, client_name="erin", traffic_limit_bytes=LIMIT)
    db.add(policy)
    db.commit()
    _run(db, node, FakePolicies({("wg", "erin"): _blocked()}))
    assert db.query(TrafficLimitNotifyState).count() == 1

    policy.traffic_limit_bytes = None
    db.commit()
    _run(db, node, FakePolicies({}))

    assert db.query(TrafficLimitNotifyState).count() == 0


def test_awg2_protocol_is_labelled_in_notifications():
    lines = _client_detail_lines("amneziawg2", "bob")

    assert any("AmneziaWG 2.0" in line for line in lines)
