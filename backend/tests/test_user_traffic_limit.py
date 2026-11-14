"""Per-user traffic accounting: `since=` window and `user_consumed_bytes` (Stage 3, Task 5).

Also covers the admin traffic-limit API (PATCH /users/{id} + traffic-counter reset) —
Stage 3, Task 11.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user, require_admin
from app.database import Base, get_db
from app.models import (
    Node,
    NodeStatus,
    OpenVpnAccessPolicy,
    User,
    UserRole,
    UserTrafficSample,
    UserTrafficStatProtocol,
    VpnConfig,
    VpnType,
)
from app.routers import users as users_router
from app.routers.users import require_admin
from app.services.user_traffic_limit import (
    reset_user_traffic_counter,
    reconcile_user_traffic_limits,
    user_consumed_bytes,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def node(db):
    n = Node(
        name="node-1",
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _make_config(db, node, user, client_name, vpn_type=VpnType.openvpn):
    c = VpnConfig(
        node_id=node.id,
        client_name=client_name,
        vpn_type=vpn_type,
        owner_id=user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _sample(db, node_id, common_name, delta_received, delta_sent, created_at):
    db.add(
        UserTrafficSample(
            node_id=node_id,
            common_name=common_name,
            protocol_type="openvpn",
            delta_received=delta_received,
            delta_sent=delta_sent,
            created_at=created_at,
        )
    )
    db.commit()


def _stat_row(db, node_id, common_name):
    db.add(
        UserTrafficStatProtocol(
            node_id=node_id,
            common_name=common_name,
            protocol_type="openvpn",
            total_received=0,
            total_sent=0,
        )
    )
    db.commit()


def test_user_consumed_bytes_sums_all_nodes_for_name(db):
    # Пользователь с одинаковым именем конфига на двух узлах (первичный + HA-тень):
    # имя берётся один раз, сумма по обоим узлам, без двойного счёта.
    n1 = Node(
        name="node-a",
        host="127.0.0.1",
        port=9101,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    n2 = Node(
        name="node-b",
        host="127.0.0.1",
        port=9102,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    db.add_all([n1, n2])
    db.commit()
    u = User(
        username="bob",
        password_hash="x",
        role="user",
        is_active=True,
        can_create_configs=True,
        panel_login_enabled=True,
        provision_state="unmanaged",
        traffic_limit_bytes=1000,
        traffic_counter_reset_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(u)
    db.commit()
    db.add_all(
        [
            VpnConfig(node_id=n1.id, client_name="alice", vpn_type=VpnType.openvpn, owner_id=u.id),
            VpnConfig(node_id=n2.id, client_name="alice", vpn_type=VpnType.openvpn, owner_id=u.id),
        ]
    )
    reset = u.traffic_counter_reset_at
    _stat_row(db, n1.id, "alice")
    _stat_row(db, n2.id, "alice")
    _sample(db, n1.id, "alice", 300, 0, reset + timedelta(hours=1))  # counted
    _sample(db, n2.id, "alice", 200, 0, reset + timedelta(hours=2))  # counted (реплика того же имени)
    _sample(db, n1.id, "alice", 999, 0, reset - timedelta(hours=1))  # до сброса — не считается
    _sample(db, n1.id, "other", 50, 0, reset + timedelta(hours=3))  # чужое имя — не считается

    assert user_consumed_bytes(db, u) == 500, user_consumed_bytes(db, u)


class _FeatureService:
    def __init__(self, traffic_sync: bool = True):
        self.traffic_sync = traffic_sync

    def is_enabled(self, key: str) -> bool:
        if key == "traffic_sync":
            return self.traffic_sync
        return True


def _make_policy_row(db, node, client_name, reason=None, permanent=False):
    row = OpenVpnAccessPolicy(
        node_id=node.id,
        client_name=client_name,
        is_temp_blocked=False,
        is_permanent_blocked=permanent,
        block_reason=reason,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_enforce_blocks_when_consumed_ge_limit(db, node, monkeypatch):
    monkeypatch.setattr("app.services.user_traffic_limit.get_feature_service", lambda: _FeatureService(True))
    u = User(
        username="dave",
        password_hash="x",
        role="user",
        is_active=True,
        can_create_configs=True,
        panel_login_enabled=True,
        provision_state="unmanaged",
        traffic_limit_bytes=1000,
        traffic_counter_reset_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(u)
    db.commit()
    cfg = _make_config(db, node, u, "dave")
    _make_policy_row(db, node, "dave")
    reset = u.traffic_counter_reset_at
    _stat_row(db, node.id, "dave")
    _sample(db, node.id, "dave", 1000, 0, reset + timedelta(hours=1))

    result = reconcile_user_traffic_limits(db)
    db.refresh(u)
    db.refresh(cfg)
    assert result["blocked"] == 1, result
    assert u.traffic_limit_blocked is True
    row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="dave").one()
    assert row.block_reason == "user_traffic_limit"


def test_enforce_unblocks_only_user_traffic_limit_keeps_manual(db, node, monkeypatch):
    monkeypatch.setattr("app.services.user_traffic_limit.get_feature_service", lambda: _FeatureService(True))
    u = User(
        username="eve",
        password_hash="x",
        role="user",
        is_active=True,
        can_create_configs=True,
        panel_login_enabled=True,
        provision_state="unmanaged",
        traffic_limit_bytes=100,
        traffic_limit_blocked=True,
        traffic_counter_reset_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(u)
    db.commit()
    cfg_a = _make_config(db, node, u, "eve-a")
    cfg_b = _make_config(db, node, u, "eve-b")
    _make_policy_row(db, node, "eve-a", reason="user_traffic_limit", permanent=True)
    _make_policy_row(db, node, "eve-b", reason="manual_permanent", permanent=True)
    db.commit()

    u.traffic_limit_bytes = 10**12
    db.commit()
    result = reconcile_user_traffic_limits(db)
    db.refresh(u)
    assert result["unblocked"] == 1, result
    assert u.traffic_limit_blocked is False
    row_a = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="eve-a").one()
    row_b = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="eve-b").one()
    assert row_a.block_reason != "user_traffic_limit"
    assert row_b.block_reason == "manual_permanent" and row_b.is_permanent_blocked


def test_traffic_sync_off_reconcile_lifts_blocks(db, node, monkeypatch):
    monkeypatch.setattr("app.services.user_traffic_limit.get_feature_service", lambda: _FeatureService(False))
    u = User(
        username="gus",
        password_hash="x",
        role="user",
        is_active=True,
        can_create_configs=True,
        panel_login_enabled=True,
        provision_state="unmanaged",
        traffic_limit_bytes=100,
        traffic_limit_blocked=True,
    )
    db.add(u)
    db.commit()
    _make_config(db, node, u, "gus")
    _make_policy_row(db, node, "gus", reason="user_traffic_limit", permanent=True)

    result = reconcile_user_traffic_limits(db)
    db.refresh(u)
    assert result["unblocked"] == 1, result
    assert u.traffic_limit_blocked is False
    row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="gus").one()
    assert row.block_reason != "user_traffic_limit"


def test_reset_user_traffic_counter(db, node, monkeypatch):
    monkeypatch.setattr("app.services.user_traffic_limit.get_feature_service", lambda: _FeatureService(True))
    u = User(
        username="hal",
        password_hash="x",
        role="user",
        is_active=True,
        can_create_configs=True,
        panel_login_enabled=True,
        provision_state="unmanaged",
        traffic_limit_bytes=100,
        traffic_limit_blocked=True,
        traffic_counter_reset_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db.add(u)
    db.commit()
    _make_config(db, node, u, "hal")
    _make_policy_row(db, node, "hal", reason="user_traffic_limit", permanent=True)

    before = u.traffic_counter_reset_at
    reset_user_traffic_counter(db, user=u, actor="admin")
    db.refresh(u)
    assert u.traffic_counter_reset_at is not None
    assert u.traffic_counter_reset_at > before
    assert u.traffic_limit_blocked is False
    row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="hal").one()
    assert row.block_reason != "user_traffic_limit"


# ---------------------------------------------------------------------------
# Task 11: админский API лимита трафика (PATCH /users/{id}, сброс счётчика)
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(db):
    u = User(
        username="admin",
        password_hash="x",
        role=UserRole.admin,
        is_active=True,
        theme="dark",
        timezone="",
        last_client_timezone="",
        noc_daily_time="",
        noc_weekly_dow="",
        noc_weekly_time="",
        can_create_configs=True,
        can_manage_configs=True,
        panel_login_enabled=True,
        provision_state="unmanaged",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def regular_user(db):
    u = User(
        username="ivan",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        theme="dark",
        timezone="",
        last_client_timezone="",
        noc_daily_time="",
        noc_weekly_dow="",
        noc_weekly_time="",
        can_create_configs=True,
        can_manage_configs=False,
        panel_login_enabled=True,
        provision_state="unmanaged",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def api(db, admin_user, monkeypatch):
    monkeypatch.setattr("app.routers.users.get_feature_service", lambda: _FeatureService(True))
    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    adapter.write_config_file.return_value = None
    adapter.get_profile_files.return_value = []
    monkeypatch.setattr("app.services.user_blocks.get_adapter_for_node", lambda node: adapter)
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: admin_user
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return TestClient(app)


def test_patch_sets_limit_and_reset_at(api, db, regular_user):
    r = api.patch(
        f"/api/users/{regular_user.id}",
        json={"traffic_limit_bytes": 100_000_000_000},
    )
    assert r.status_code == 200, r.text
    db.refresh(regular_user)
    assert regular_user.traffic_limit_bytes == 100_000_000_000
    assert regular_user.traffic_counter_reset_at is not None


def test_patch_null_clears_limit_and_lifts_block(api, db, node, regular_user):
    _make_config(db, node, regular_user, "ivan")
    _make_policy_row(db, node, "ivan", reason="user_traffic_limit", permanent=True)
    regular_user.traffic_limit_bytes = 1000
    regular_user.traffic_limit_blocked = True
    db.commit()

    r = api.patch(f"/api/users/{regular_user.id}", json={"traffic_limit_bytes": None})
    assert r.status_code == 200, r.text
    db.refresh(regular_user)
    assert regular_user.traffic_limit_bytes is None
    assert regular_user.traffic_limit_blocked is False
    row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="ivan").one()
    assert row.block_reason != "user_traffic_limit"
