"""WireGuard access policy service tests (ported from AdminAntizapret test_wg_access_policy_service)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, WgAccessPolicy
from app.services.access_policy import AccessPolicyService
from app.services.traffic_limit import TrafficLimitExceededError


@pytest.fixture()
def wg_policy_env(tmp_path: Path):
    db_path = tmp_path / "wg_policy.db"
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
    adapter = MagicMock()

    svc = AccessPolicyService(
        session,
        antizapret_path=Path("/tmp/az"),
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
    yield session, node, svc, consumed_by_client, adapter
    patcher.stop()
    session.close()


def _utc_now():
    return datetime.now(timezone.utc)


def test_wg_unblock_rejects_expired_access(wg_policy_env):
    session, _node, svc, _consumed, _adapter = wg_policy_env
    session.add(
        WgAccessPolicy(
            node_id=svc.node_id,
            client_name="expired-user",
            expires_at=_utc_now() - timedelta(days=1),
        )
    )
    session.commit()

    with pytest.raises(ValueError, match="истечении срока"):
        svc.wg_unblock("expired-user", actor="admin")


def test_extend_after_expiry_unblocks_client(wg_policy_env):
    session, _node, svc, _consumed, _adapter = wg_policy_env
    session.add(
        WgAccessPolicy(
            node_id=svc.node_id,
            client_name="renew-user",
            expires_at=_utc_now() - timedelta(hours=2),
        )
    )
    session.commit()

    svc.wg_set_expiry("renew-user", 30, extend=True, actor="admin")
    svc.reconcile_wg("renew-user", apply_runtime=False)
    state = svc.get_wg_policy("renew-user")

    assert state["is_blocked"] is False
    assert state["block_mode"] == "none"


def test_traffic_limit_blocks_client(wg_policy_env):
    _session, _node, svc, consumed, _adapter = wg_policy_env
    consumed["traffic-user"] = 1500
    svc.wg_set_traffic_limit("traffic-user", 1000, actor="admin")
    svc.reconcile_wg("traffic-user", apply_runtime=False)
    state = svc.get_wg_policy("traffic-user")

    assert state["is_blocked"] is True
    assert state["block_mode"] == "traffic_limit"


def test_wg_unblock_rejects_traffic_limit(wg_policy_env):
    _session, _node, svc, consumed, _adapter = wg_policy_env
    consumed["traffic-user"] = 1500
    svc.wg_set_traffic_limit("traffic-user", 1000, actor="admin")

    with pytest.raises(TrafficLimitExceededError):
        svc.wg_unblock("traffic-user", actor="admin")


def test_increasing_traffic_limit_unblocks_client(wg_policy_env):
    _session, _node, svc, consumed, _adapter = wg_policy_env
    consumed["traffic-user"] = 1500
    svc.wg_set_traffic_limit("traffic-user", 1000, actor="admin")
    svc.wg_set_traffic_limit("traffic-user", 2000, actor="admin")
    svc.reconcile_wg("traffic-user", apply_runtime=False)
    state = svc.get_wg_policy("traffic-user")

    assert state["is_blocked"] is False
    assert state["block_mode"] == "none"


def test_traffic_limit_stores_period_days(wg_policy_env):
    session, _node, svc, consumed, _adapter = wg_policy_env
    consumed[("period-user", 7)] = 500
    svc.wg_set_traffic_limit("period-user", 1000, period_days=7, actor="admin")
    row = session.query(WgAccessPolicy).filter_by(client_name="period-user").first()
    svc.reconcile_wg("period-user", apply_runtime=False)
    state = svc.get_wg_policy("period-user")

    assert row.traffic_limit_period_days == 7
    assert state["traffic_limit_period_days"] == 7
    assert state["traffic_limit_period_label"] == "за неделю (пн–вс)"
    assert state["is_blocked"] is False


def test_traffic_limit_auto_unblocks_on_new_period(wg_policy_env):
    _session, _node, svc, consumed, _adapter = wg_policy_env
    consumed[("traffic-user", 1)] = 1500
    svc.wg_set_traffic_limit("traffic-user", 1000, period_days=1, actor="admin")
    blocked = svc.get_wg_policy("traffic-user")
    assert blocked["is_blocked"] is True

    consumed[("traffic-user", 1)] = 0
    svc.reconcile_wg("traffic-user", apply_runtime=False)
    state = svc.get_wg_policy("traffic-user")

    assert state["is_blocked"] is False
    assert state["block_mode"] == "none"


def test_reconcile_all_wg_policies_batches_runtime(wg_policy_env):
    session, _node, svc, _consumed, adapter = wg_policy_env
    session.add_all(
        [
            WgAccessPolicy(
                node_id=svc.node_id,
                client_name="blocked-a",
                is_permanent_blocked=True,
                block_reason="manual_permanent",
            ),
            WgAccessPolicy(
                node_id=svc.node_id,
                client_name="open-b",
            ),
        ]
    )
    session.commit()

    result = svc.reconcile_all_wg_policies(apply_runtime=True, sync_all_runtime=True)

    assert result["wg_policy_reconcile"] == "ok"
    assert "blocked-a" in result["blocked_clients"]
    assert "open-b" in result["unblocked_clients"]
    adapter.block_wireguard_client_runtime.assert_called_with("blocked-a")
    adapter.unblock_wireguard_client_runtime.assert_called_with("open-b")


def test_reconcile_all_wg_policies_skips_runtime_when_unchanged(wg_policy_env):
    session, _node, svc, _consumed, adapter = wg_policy_env
    session.add_all(
        [
            WgAccessPolicy(
                node_id=svc.node_id,
                client_name="blocked-a",
                is_permanent_blocked=True,
                block_reason="manual_permanent",
            ),
            WgAccessPolicy(node_id=svc.node_id, client_name="open-b"),
        ]
    )
    session.commit()

    svc.reconcile_all_wg_policies(apply_runtime=True, sync_all_runtime=True)
    adapter.reset_mock()
    svc.wg_runtime_calls = 0

    result = svc.reconcile_all_wg_policies(apply_runtime=True, sync_all_runtime=False)

    assert result["clients_changed"] == 0
    assert result["wg_runtime_calls"] == 0
    adapter.block_wireguard_client_runtime.assert_not_called()
    adapter.unblock_wireguard_client_runtime.assert_not_called()


def test_reapply_blocked_after_unblock(wg_policy_env):
    session, _node, svc, _consumed, adapter = wg_policy_env
    session.add_all(
        [
            WgAccessPolicy(node_id=svc.node_id, client_name="open-a"),
            WgAccessPolicy(
                node_id=svc.node_id,
                client_name="blocked-b",
                is_permanent_blocked=True,
                block_reason="manual_permanent",
            ),
        ]
    )
    session.commit()
    svc.wg_permanent_block("open-a", actor="admin")
    adapter.reset_mock()

    svc.wg_unblock("open-a", actor="admin")

    adapter.unblock_wireguard_client_runtime.assert_called_once_with("open-a")
    adapter.block_wireguard_client_runtime.assert_called_once_with("blocked-b")


def test_reconcile_all_wg_policies_isolated_per_node(wg_policy_env):
    session, local, svc, _consumed, adapter = wg_policy_env
    remote = Node(
        name="remote",
        host="10.0.0.2",
        port=9100,
        is_local=False,
        status=NodeStatus.online,
    )
    session.add(remote)
    session.commit()
    session.add(
        WgAccessPolicy(
            node_id=remote.id,
            client_name="remote-only",
            is_permanent_blocked=True,
            block_reason="manual_permanent",
        )
    )
    session.commit()

    result = svc.reconcile_all_wg_policies(apply_runtime=True, node_id=local.id)

    assert result["node_id"] == local.id
    assert "remote-only" not in result["blocked_clients"]
    for call in adapter.block_wireguard_client_runtime.call_args_list:
        assert call.args[0] != "remote-only"
