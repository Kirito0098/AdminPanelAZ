"""user_blocks.apply_user_block / lift_user_block — shared user-level VPN block helpers."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Node,
    NodeStatus,
    OpenVpnAccessPolicy,
    User,
    VpnConfig,
    VpnType,
)
from app.services.user_blocks import apply_user_block, lift_user_block


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _fake_adapter(monkeypatch):
    """Hide the real node adapter (filesystem) from user_blocks policy service."""
    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    adapter.write_config_file.return_value = None
    adapter.ensure_openvpn_ban_check.return_value = None
    monkeypatch.setattr("app.services.user_blocks.get_adapter_for_node", lambda node: adapter)


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
def user(db, node):
    u = User(
        username="alice",
        password_hash="x",
        role="user",
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


def _policy_row(db, config):
    if config.vpn_type == VpnType.openvpn:
        model = OpenVpnAccessPolicy
        name = config.client_name
    else:
        model = OpenVpnAccessPolicy
        name = config.client_name.strip().lower()
    return db.query(model).filter_by(node_id=config.node_id, client_name=name).first()


@pytest.fixture
def user_with_three_configs(db, node, user):
    for i in range(3):
        _make_config(db, node, user, f"cfg-{i}")
    return user


@pytest.fixture
def user_with_config(db, node, user):
    _make_config(db, node, user, "cfg-solo")
    return user


def test_apply_user_block_sets_reason_on_all_protocols(db, user_with_three_configs):
    result = apply_user_block(db, user_with_three_configs, "user_suspended", actor="admin")
    assert result["blocked"] == 3
    assert result["skipped_offline"] == 0
    assert result["errors"] == []
    for config in user_with_three_configs.vpn_configs:
        row = _policy_row(db, config)
        assert row.is_permanent_blocked is True
        assert row.block_reason == "user_suspended"


def test_lift_user_suspended_clears_only_that_reason(db, user_with_config):
    apply_user_block(db, user_with_config, "user_suspended", actor="a")
    lift_user_block(db, user_with_config, "user_suspended", actor="a")
    db.refresh(user_with_config)
    assert user_with_config.suspended_at is None
    for config in user_with_config.vpn_configs:
        row = _policy_row(db, config)
        assert row.is_permanent_blocked is False
        assert row.block_reason != "user_suspended"
