"""OpenVPN access policy service tests (ported from AdminAntizapret)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, OpenVpnAccessPolicy
from app.services.access_policy import AccessPolicyService
from app.services.traffic_limit import TrafficLimitExceededError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def ovpn_policy_env(tmp_path: Path):
    db_path = tmp_path / "ovpn_policy.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    node = Node(
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    session.add(node)
    session.commit()

    consumed_by_client: dict = {}
    banned_clients: set[str] = set()
    adapter = MagicMock()

    def _read_config_file(name: str) -> str:
        if name == "banned_clients":
            return "\n".join(sorted(banned_clients)) + ("\n" if banned_clients else "")
        return ""

    def _write_config_file(name: str, content: str) -> None:
        if name == "banned_clients":
            banned_clients.clear()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    banned_clients.add(line)

    adapter.read_config_file.side_effect = _read_config_file
    adapter.write_config_file.side_effect = _write_config_file
    adapter.ensure_openvpn_ban_check.return_value = None

    svc = AccessPolicyService(
        session,
        antizapret_path=tmp_path / "az",
        node_id=node.id,
        adapter=adapter,
    )

    def _get_consumed(client_name, period_days=None):
        key = (client_name, period_days) if period_days is not None else client_name
        if key in consumed_by_client:
            return int(consumed_by_client[key])
        return int(consumed_by_client.get(client_name, 0))

    patcher = patch.object(
        svc,
        "_consumed_bytes",
        side_effect=lambda name, period_days=None: _get_consumed(name, period_days),
    )
    patcher.start()
    yield session, node, svc, consumed_by_client, banned_clients, adapter
    patcher.stop()
    session.close()


def test_temp_block_reapplies_from_now(ovpn_policy_env):
    session, _node, svc, _consumed, banned, _adapter = ovpn_policy_env
    svc.openvpn_temp_block("alice", 1, actor="admin")
    first = session.query(OpenVpnAccessPolicy).filter_by(client_name="alice").first()
    first_until = first.block_until

    svc.openvpn_temp_block("alice", 10, actor="admin")
    second = session.query(OpenVpnAccessPolicy).filter_by(client_name="alice").first()

    assert first_until is not None
    assert second.block_until is not None
    assert second.block_until > first_until
    second_until = second.block_until
    if second_until.tzinfo is None:
        second_until = second_until.replace(tzinfo=timezone.utc)
    assert second_until <= _utc_now() + timedelta(days=10, minutes=1)
    assert "alice" in banned


def test_permanent_to_temp_switch(ovpn_policy_env):
    session, _node, svc, _consumed, _banned, _adapter = ovpn_policy_env
    svc.openvpn_permanent_block("bob", actor="admin")
    svc.openvpn_temp_block("bob", 3, actor="admin")
    row = session.query(OpenVpnAccessPolicy).filter_by(client_name="bob").first()

    assert row.is_temp_blocked is True
    assert row.is_permanent_blocked is False
    assert row.block_reason == "temp"
    assert row.block_until is not None


def test_unblock_clears_banlist(ovpn_policy_env):
    session, _node, svc, _consumed, banned, _adapter = ovpn_policy_env
    svc.openvpn_permanent_block("carol", actor="admin")
    assert "carol" in banned
    svc.openvpn_unblock("carol", actor="admin")
    row = session.query(OpenVpnAccessPolicy).filter_by(client_name="carol").first()

    assert row.is_temp_blocked is False
    assert row.is_permanent_blocked is False
    assert row.block_reason is None
    assert "carol" not in banned


def test_traffic_limit_blocks_client(ovpn_policy_env):
    _session, _node, svc, consumed, banned, _adapter = ovpn_policy_env
    consumed["dave"] = 2048
    svc.openvpn_set_traffic_limit("dave", 1024, actor="admin")
    state = svc.get_openvpn_policy("dave")

    assert state["is_blocked"] is True
    assert state["block_mode"] == "traffic_limit"
    assert "dave" in banned


def test_reconcile_all_does_not_mark_traffic_limit_as_permanent(ovpn_policy_env):
    session, _node, svc, consumed, _banned, _adapter = ovpn_policy_env
    consumed["dave"] = 2048
    svc.openvpn_set_traffic_limit("dave", 1024, actor="admin")
    svc.reconcile_all_traffic_limits()
    row = session.query(OpenVpnAccessPolicy).filter_by(client_name="dave").first()
    state = svc.get_openvpn_policy("dave")

    assert row.is_permanent_blocked is False
    assert state["block_mode"] == "traffic_limit"


def test_clear_block_rejects_traffic_limit(ovpn_policy_env):
    _session, _node, svc, consumed, _banned, _adapter = ovpn_policy_env
    consumed["dave"] = 2048
    svc.openvpn_set_traffic_limit("dave", 1024, actor="admin")
    with pytest.raises(TrafficLimitExceededError):
        svc.openvpn_unblock("dave", actor="admin")


def test_traffic_limit_period_blocks_by_window(ovpn_policy_env):
    _session, _node, svc, consumed, _banned, _adapter = ovpn_policy_env
    consumed[("dave", 1)] = 2048
    svc.openvpn_set_traffic_limit("dave", 1024, period_days=1, actor="admin")
    state = svc.get_openvpn_policy("dave")

    assert state["is_blocked"] is True
    assert state["traffic_limit_period_days"] == 1
    assert state["traffic_limit_period_label"] == "за сутки (календарный день)"


def test_traffic_limit_auto_unblocks_on_new_period(ovpn_policy_env):
    _session, _node, svc, consumed, banned, _adapter = ovpn_policy_env
    consumed[("dave", 7)] = 5000
    svc.openvpn_set_traffic_limit("dave", 1024, period_days=7, actor="admin")
    blocked = svc.get_openvpn_policy("dave")
    assert blocked["is_blocked"] is True
    assert "dave" in banned

    consumed[("dave", 7)] = 0
    svc.reconcile_openvpn("dave")
    state = svc.get_openvpn_policy("dave")

    assert state["is_blocked"] is False
    assert state["block_mode"] == "none"
    assert "dave" not in banned


def test_increasing_traffic_limit_unblocks_client(ovpn_policy_env):
    _session, _node, svc, consumed, banned, _adapter = ovpn_policy_env
    consumed["dave"] = 2048
    svc.openvpn_set_traffic_limit("dave", 1024, actor="admin")
    assert svc.get_openvpn_policy("dave")["is_blocked"] is True
    svc.openvpn_set_traffic_limit("dave", 4096, actor="admin")
    state = svc.get_openvpn_policy("dave")

    assert state["is_blocked"] is False
    assert state["block_mode"] == "none"
    assert "dave" not in banned


def test_reconcile_all_does_not_import_stale_traffic_banlist(ovpn_policy_env):
    session, _node, svc, consumed, banned, _adapter = ovpn_policy_env
    consumed["dave"] = 500
    svc.openvpn_set_traffic_limit("dave", 4096, actor="admin")
    banned.add("dave")
    row = session.query(OpenVpnAccessPolicy).filter_by(client_name="dave").first()
    row.block_reason = "traffic_limit"
    session.commit()

    svc.reconcile_all_traffic_limits()
    state = svc.get_openvpn_policy("dave")

    assert row.is_permanent_blocked is False
    assert state["is_blocked"] is False
    assert "dave" not in banned


def test_increasing_traffic_limit_clears_wrong_permanent_block(ovpn_policy_env):
    session, _node, svc, consumed, banned, _adapter = ovpn_policy_env
    consumed["dave"] = 500
    svc.openvpn_set_traffic_limit("dave", 4096, actor="admin")
    row = session.query(OpenVpnAccessPolicy).filter_by(client_name="dave").first()
    row.is_permanent_blocked = True
    row.block_reason = "manual_permanent"
    row.block_started_at = _utc_now()
    banned.add("dave")
    session.commit()

    svc.openvpn_set_traffic_limit("dave", 8192, actor="admin")
    state = svc.get_openvpn_policy("dave")

    assert row.is_permanent_blocked is False
    assert state["is_blocked"] is False
    assert "dave" not in banned
