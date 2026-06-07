"""Node-scoping tests for panel DB models and access policies."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, NodeStatus, OpenVpnAccessPolicy, WgAccessPolicy
from app.services.access_policy import AccessPolicyService


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    local = Node(
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    remote = Node(
        name="remote",
        host="10.0.0.2",
        port=9100,
        is_local=False,
        status=NodeStatus.online,
    )
    session.add_all([local, remote])
    session.commit()
    yield session, local, remote
    session.close()


def test_openvpn_access_policy_isolated_per_node(db_session):
    session, local, remote = db_session
    session.add(
        OpenVpnAccessPolicy(
            node_id=local.id,
            client_name="alice",
            is_permanent_blocked=True,
            block_reason="manual_permanent",
        )
    )
    session.commit()

    local_svc = AccessPolicyService(
        session,
        antizapret_path=Path("/tmp/az"),
        node_id=local.id,
        adapter=MagicMock(),
    )
    remote_svc = AccessPolicyService(
        session,
        antizapret_path=Path("/tmp/az"),
        node_id=remote.id,
        adapter=MagicMock(),
    )

    assert local_svc.get_openvpn_policy("alice")["block_mode"] == "permanent"
    assert remote_svc.get_openvpn_policy("alice")["block_mode"] == "none"


def test_wg_access_policy_isolated_per_node(db_session):
    session, local, remote = db_session
    session.add(
        WgAccessPolicy(
            node_id=local.id,
            client_name="bob",
            is_temp_blocked=True,
            block_reason="manual_temp",
            block_until=datetime.now(timezone.utc) + timedelta(days=7),
        )
    )
    session.commit()

    local_svc = AccessPolicyService(
        session,
        antizapret_path=Path("/tmp/az"),
        node_id=local.id,
        adapter=MagicMock(),
    )
    remote_svc = AccessPolicyService(
        session,
        antizapret_path=Path("/tmp/az"),
        node_id=remote.id,
        adapter=MagicMock(),
    )

    assert local_svc.get_wg_policy("bob")["block_mode"] == "temp"
    assert remote_svc.get_wg_policy("bob")["block_mode"] == "none"


def test_reconcile_all_traffic_limits_only_touches_target_node(db_session):
    session, local, remote = db_session
    session.add_all(
        [
            OpenVpnAccessPolicy(node_id=local.id, client_name="c1"),
            OpenVpnAccessPolicy(node_id=remote.id, client_name="c1"),
        ]
    )
    session.commit()

    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    svc = AccessPolicyService(
        session,
        antizapret_path=Path("/tmp/az"),
        node_id=local.id,
        adapter=adapter,
    )
    result = svc.reconcile_all_traffic_limits(node_id=local.id)

    assert result["node_id"] == local.id
    adapter.write_config_file.assert_called()
