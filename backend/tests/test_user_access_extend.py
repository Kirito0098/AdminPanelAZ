"""Extension hook: arithmetic, on_user_access_extended, set_user_access_until integration (Stage 3, Task 7)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import (
    Node,
    NodeStatus,
    OpenVpnAccessPolicy,
    UnlockCode,
    User,
    UserRole,
    VpnConfig,
    VpnType,
)
from app.routers import users as users_router
from app.routers.users import require_admin
from app.services.user_access_extend import compute_extended_access_until, on_user_access_extended
from app.services.user_subscription import set_user_access_until, get_user_access_until
from app.services.unlock_codes import (
    create_unlock_code,
    redeem_unlock_code,
    _is_manual_admin_block,
)


class _FeatureService:
    def __init__(self, states=None):
        self.states = states or {}

    def is_enabled(self, key: str) -> bool:
        return self.states.get(key, True)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _fake_adapters(monkeypatch):
    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    adapter.write_config_file.return_value = None
    adapter.ensure_openvpn_ban_check.return_value = None
    monkeypatch.setattr("app.services.user_blocks.get_adapter_for_node", lambda node: adapter)
    monkeypatch.setattr("app.services.access_until.get_adapter_for_node", lambda node: adapter)
    monkeypatch.setattr(
        "app.services.config_provisioning.get_adapter_for_node", lambda node: adapter
    )


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


@pytest.fixture
def admin_user(db):
    u = User(
        username="admin", password_hash="x", role=UserRole.admin, is_active=True,
        can_create_configs=True, can_manage_configs=True, panel_login_enabled=True,
        provision_state="unmanaged",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def regular_user(db):
    u = User(
        username="alice", password_hash="x", role=UserRole.user, is_active=True,
        can_create_configs=True, panel_login_enabled=True, provision_state="unmanaged",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_config(db, node, user, client_name, vpn_type=VpnType.openvpn):
    c = VpnConfig(
        node_id=node.id, client_name=client_name, vpn_type=vpn_type, owner_id=user.id
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _make_policy_row(db, node, client_name, reason=None, permanent=False):
    row = OpenVpnAccessPolicy(
        node_id=node.id, client_name=client_name,
        is_temp_blocked=False, is_permanent_blocked=permanent, block_reason=reason,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class _CapturedTask(SimpleNamespace):
    pass


@pytest.fixture
def captured_enqueue(monkeypatch):
    captured = {}

    def fake_enqueue(db, *, user_id, actor_username, confirm_deletions, creations_only=False):
        captured.update(
            user_id=user_id, actor_username=actor_username,
            confirm_deletions=confirm_deletions, creations_only=creations_only,
        )
        return _CapturedTask(id="task-1")

    monkeypatch.setattr("app.services.user_provisioning.enqueue_user_provision", fake_enqueue)
    return captured


# ---------------------------------------------------------------- arithmetic


def test_compute_extended_from_active_term():
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    current = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert compute_extended_access_until(current, 30, now=now) == datetime(
        2026, 12, 1, tzinfo=timezone.utc
    )


def test_compute_extended_from_expired_term():
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    current = datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert compute_extended_access_until(current, 30, now=now) == datetime(
        2026, 11, 17, tzinfo=timezone.utc
    )


def test_compute_extended_none_current():
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    assert compute_extended_access_until(None, 30, now=now) == datetime(
        2026, 11, 17, tzinfo=timezone.utc
    )


# ------------------------------------------------- set_user_access_until hook


def test_set_user_access_until_extension_enqueues_creations_only(
    db, regular_user, node, monkeypatch, captured_enqueue
):
    monkeypatch.setattr(
        "app.services.user_access_extend.get_feature_service",
        lambda: _FeatureService({"user_provisioning": True}),
    )
    regular_user.client_base_name = "vpn"
    regular_user.plan_config_indexes = "[1]"
    regular_user.access_until = datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    db.commit()

    new_until = datetime(2026, 12, 1, tzinfo=timezone.utc)
    set_user_access_until(db, regular_user, new_until, actor="admin")
    db.refresh(regular_user)

    assert regular_user.access_until == new_until.replace(tzinfo=None)
    assert regular_user.traffic_counter_reset_at is not None
    assert captured_enqueue["creations_only"] is True
    assert captured_enqueue["user_id"] == regular_user.id


def test_set_user_access_until_no_extension_when_same_or_past(
    db, regular_user, monkeypatch, captured_enqueue
):
    monkeypatch.setattr(
        "app.services.user_access_extend.get_feature_service",
        lambda: _FeatureService({"user_provisioning": True}),
    )
    regular_user.client_base_name = "vpn"
    now = datetime(2026, 10, 18, tzinfo=timezone.utc).replace(tzinfo=None)
    regular_user.access_until = now + timedelta(days=10)
    db.commit()

    set_user_access_until(db, regular_user, now + timedelta(days=10), actor="admin")
    assert captured_enqueue == {}

    # Clearing access_until to NULL must not reset traffic.
    set_user_access_until(db, regular_user, None, actor="admin")
    db.refresh(regular_user)
    assert regular_user.access_until is None
    assert captured_enqueue == {}


def test_extension_resets_traffic_and_lifts_user_traffic_limit(
    db, regular_user, node, monkeypatch, captured_enqueue
):
    monkeypatch.setattr(
        "app.services.user_access_extend.get_feature_service",
        lambda: _FeatureService({"user_provisioning": True}),
    )
    regular_user.traffic_limit_bytes = 1000
    regular_user.traffic_limit_blocked = True
    regular_user.traffic_counter_reset_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db.commit()
    _make_config(db, node, regular_user, "alice")
    _make_policy_row(db, node, "alice", reason="user_traffic_limit", permanent=True)

    set_user_access_until(
        db, regular_user,
        datetime(2026, 12, 1, tzinfo=timezone.utc),
        actor="admin",
    )
    db.refresh(regular_user)
    assert regular_user.traffic_limit_blocked is False
    assert regular_user.traffic_counter_reset_at is not None
    row = (
        db.query(OpenVpnAccessPolicy)
        .filter_by(node_id=node.id, client_name="alice")
        .one()
    )
    assert row.block_reason != "user_traffic_limit"


# ---------------------------------------------------------------- API extend


def test_extend_endpoint(db, admin_user, regular_user, node, monkeypatch, captured_enqueue):
    monkeypatch.setattr("app.routers.users.get_feature_service", lambda: _FeatureService())
    monkeypatch.setattr("app.services.user_access_extend.get_feature_service", lambda: _FeatureService())
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: admin_user
    api = TestClient(app)

    regular_user.client_base_name = "vpn"
    regular_user.access_until = datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    db.commit()

    r = api.post(f"/api/users/{regular_user.id}/extend", json={"days": 30})
    assert r.status_code == 200, r.text
    db.refresh(regular_user)
    assert regular_user.access_until is not None
    assert regular_user.access_until > datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    assert regular_user.traffic_counter_reset_at is not None
    assert captured_enqueue["creations_only"] is True


def test_extend_endpoint_404_and_feature_off(db, admin_user, regular_user, monkeypatch):
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: admin_user
    api = TestClient(app)

    # Модуль выключен — 403 независимо от существования пользователя.
    monkeypatch.setattr("app.routers.users.get_feature_service", lambda: _FeatureService({"user_provisioning": False}))
    r = api.post(f"/api/users/{regular_user.id}/extend", json={"days": 30})
    assert r.status_code == 403, r.text

    # Пользователя нет — 404.
    monkeypatch.setattr("app.routers.users.get_feature_service", lambda: _FeatureService())
    r = api.post("/api/users/999999/extend", json={"days": 30})
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------- redeem owner path -> hook


def test_redeem_owner_extends_and_triggers_hook(
    db, regular_user, node, monkeypatch, captured_enqueue
):
    monkeypatch.setattr("app.services.unlock_codes.get_feature_service", lambda: _FeatureService())
    monkeypatch.setattr(
        "app.services.user_access_extend.get_feature_service",
        lambda: _FeatureService({"user_provisioning": True}),
    )
    regular_user.client_base_name = "vpn"
    regular_user.plan_config_indexes = "[1]"
    regular_user.access_until = datetime(2026, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    regular_user.traffic_limit_bytes = 100
    regular_user.traffic_limit_blocked = True
    regular_user.telegram_id = "111"
    db.commit()
    _make_config(db, node, regular_user, "alice")
    _make_policy_row(db, node, "alice", reason="user_traffic_limit", permanent=True)
    previous_access_until = get_user_access_until(regular_user)

    code = create_unlock_code(
        db,
        grant_days=30,
        protocols=["openvpn"],
        mode="single",
        max_redemptions=1,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=regular_user,
        code="REDEEM-OWN-1",
    )
    result = redeem_unlock_code(
        db, code=code.code, client_name="alice", node_id=node.id, user_id=regular_user.id
    )
    db.refresh(regular_user)
    assert result["grant_days"] == 30
    assert regular_user.traffic_limit_blocked is False
    assert regular_user.traffic_counter_reset_at is not None
    assert get_user_access_until(regular_user) > previous_access_until
    assert captured_enqueue["creations_only"] is True
    row = (
        db.query(OpenVpnAccessPolicy)
        .filter_by(node_id=node.id, client_name="alice")
        .one()
    )
    assert row.block_reason != "user_traffic_limit"


def test_is_manual_admin_block_traffic_limit_allows_redeem(db, node):
    row = _make_policy_row(db, node, "alice", reason="user_traffic_limit", permanent=True)
    assert _is_manual_admin_block(row) is False


def test_is_manual_admin_block_suspended_refuses_redeem(db, node):
    row = _make_policy_row(db, node, "alice", reason="user_suspended", permanent=True)
    assert _is_manual_admin_block(row) is True


def test_redeem_refused_when_user_suspended(db, regular_user, node, monkeypatch):
    monkeypatch.setattr("app.services.unlock_codes.get_feature_service", lambda: _FeatureService())
    _make_config(db, node, regular_user, "alice")
    _make_policy_row(db, node, "alice", reason="user_suspended", permanent=True)
    code = create_unlock_code(
        db,
        grant_days=30,
        protocols=["openvpn"],
        mode="single",
        max_redemptions=1,
        code_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        creator=regular_user,
        code="REDEEM-SUSP-1",
    )
    with pytest.raises(ValueError, match="Доступ приостановлен администратором"):
        redeem_unlock_code(
            db, code=code.code, client_name="alice", node_id=node.id, user_id=regular_user.id
        )

