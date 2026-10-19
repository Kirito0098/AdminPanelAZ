"""Suspend / resume API + create-while-suspended (Stage 3, Task 4)."""

from datetime import datetime, timezone
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
    User,
    UserRole,
    VpnConfig,
    VpnType,
)
from app.routers import users as users_router
from app.routers.users import require_admin
from app.services.user_blocks import apply_user_block, lift_user_block


class _FeatureService:
    def is_enabled(self, key: str) -> bool:
        return True


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _patch_services(monkeypatch):
    """user_provisioning enabled; real node adapters hidden behind fakes."""
    monkeypatch.setattr("app.routers.users.get_feature_service", lambda: _FeatureService())
    monkeypatch.setattr(
        "app.services.config_provisioning.get_feature_service", lambda: _FeatureService()
    )

    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    adapter.read_profile_file.return_value = ""
    adapter.get_profile_files.return_value = []
    adapter.write_config_file.return_value = None
    adapter.ensure_openvpn_ban_check.return_value = None
    adapter.add_openvpn_client.return_value = None
    adapter.delete_openvpn_client.return_value = None
    adapter.awg2_add_client.return_value = None
    adapter.awg2_delete_client.return_value = None
    adapter.add_wireguard_client.return_value = None
    adapter.delete_wireguard_client.return_value = None
    monkeypatch.setattr("app.services.user_blocks.get_adapter_for_node", lambda node: adapter)
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
        username="alice",
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
def api(db, admin_user):
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: admin_user
    return TestClient(app)


def _make_config(db, node, owner, client_name="cfg-1", vpn_type=VpnType.openvpn):
    c = VpnConfig(
        node_id=node.id,
        client_name=client_name,
        vpn_type=vpn_type,
        owner_id=owner.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _policy_row(db, node, client_name, vpn_type=VpnType.openvpn):
    return (
        db.query(OpenVpnAccessPolicy)
        .filter_by(node_id=node.id, client_name=client_name)
        .first()
    )


def test_suspend_blocks_all_configs(api, db, node, regular_user):
    _make_config(db, node, regular_user, "cfg-1")
    _make_config(db, node, regular_user, "cfg-2")
    r = api.post(
        f"/api/users/{regular_user.id}/suspend",
        json={"reason": "неоплата", "show_reason": True, "notify_telegram": False},
    )
    assert r.status_code == 200, r.text
    db.refresh(regular_user)
    assert regular_user.suspended_at is not None
    assert regular_user.suspend_reason == "неоплата"
    for config in regular_user.vpn_configs:
        row = _policy_row(db, node, config.client_name)
        assert row.is_permanent_blocked is True
        assert row.block_reason == "user_suspended"


def test_resume_lifts_only_user_suspended(api, db, node, regular_user, admin_user):
    _make_config(db, node, regular_user, "cfg-1")
    regular_user.suspended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    regular_user.traffic_limit_blocked = True
    db.commit()
    apply_user_block(db, regular_user, "user_suspended", actor=admin_user.username)
    r = api.post(f"/api/users/{regular_user.id}/resume", json={})
    assert r.status_code == 200, r.text
    db.refresh(regular_user)
    assert regular_user.suspended_at is None
    row = _policy_row(db, node, "cfg-1")
    assert row.block_reason == "user_traffic_limit"


def test_provision_config_while_suspended_creates_blocked(db, node, regular_user, admin_user):
    regular_user.suspended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    from app.services.config_provisioning import provision_config

    config, _warning = provision_config(
        db,
        node=node,
        client_name="ivan",
        vpn_type=VpnType.openvpn,
        owner=regular_user,
        actor=admin_user,
        notify=False,
    )
    row = _policy_row(db, node, "ivan")
    assert row.block_reason == "user_suspended"
    assert config.owner_id == regular_user.id
