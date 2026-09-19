from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AmneziaWg2AccessPolicy, Node, NodeStatus, OpenVpnAccessPolicy, User, UserRole, VpnConfig, VpnType, WgAccessPolicy
from app.services.access_until import set_access_until
from app.services import user_subscription as usub


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


def _make_node(db):
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


def _adapter():
    adapter = MagicMock()
    adapter.read_config_file.return_value = ""
    adapter.write_config_file.return_value = None
    adapter.ensure_openvpn_ban_check.return_value = None
    adapter.block_wireguard_client_runtime.return_value = {"success": True}
    adapter.unblock_wireguard_client_runtime.return_value = {"success": True}
    adapter.block_awg2_client_runtime.return_value = {"success": True}
    adapter.unblock_awg2_client_runtime.return_value = {"success": True}
    return adapter


def _make_owned_client(db, *, node_id: int, owner_id: int, client_name: str, protocols: list[VpnType]) -> None:
    for vpn_type in protocols:
        db.add(
            VpnConfig(
                node_id=node_id,
                client_name=client_name,
                vpn_type=vpn_type,
                owner_id=owner_id,
            )
        )
    db.commit()


def test_user_subscription_expired_null_is_unlimited(db):
    user = User(username="u1", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()
    assert usub.user_subscription_expired(user) is False


def test_user_subscription_expired_past(db):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    user = User(
        username="u2",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=past.replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    assert usub.user_subscription_expired(user) is True


def test_user_subscription_expired_future(db):
    future = datetime.now(timezone.utc) + timedelta(days=7)
    user = User(
        username="u3",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=future.replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    assert usub.user_subscription_expired(user) is False


def test_set_user_access_until_syncs_owned_clients(db):
    node = _make_node(db)
    future = datetime.now(timezone.utc) + timedelta(days=14)
    user = User(username="owner-sync", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user.id,
        client_name="Alice",
        protocols=[VpnType.openvpn, VpnType.wireguard],
    )

    with patch("app.services.access_until.get_adapter_for_node", return_value=_adapter()):
        updated = usub.set_user_access_until(db, user, future, actor="admin")

    assert usub.get_user_access_until(updated) == future
    ovpn = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
    wg = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    assert ovpn.access_until == future.replace(tzinfo=None)
    assert wg.expires_at == future.replace(tzinfo=None)


def test_clear_access_expired_skips_permanent_block(db):
    node = _make_node(db)
    user = User(
        username="owner-clear",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=(datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user.id,
        client_name="Alice",
        protocols=[VpnType.wireguard, VpnType.amneziawg2],
    )
    past = datetime.now(timezone.utc) - timedelta(days=1)
    db.add(
        WgAccessPolicy(
            node_id=node.id,
            client_name="alice",
            expires_at=past.replace(tzinfo=None),
            is_temp_blocked=False,
            is_permanent_blocked=True,
            block_reason="access_expired",
        )
    )
    db.add(
        AmneziaWg2AccessPolicy(
            node_id=node.id,
            client_name="alice",
            access_until=past.replace(tzinfo=None),
            is_temp_blocked=False,
            is_permanent_blocked=False,
            block_reason="access_expired",
        )
    )
    db.commit()

    with patch("app.services.access_until.get_adapter_for_node", return_value=_adapter()):
        result = usub.clear_access_expired_for_user(db, user, actor="admin")

    wg = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    awg2 = db.query(AmneziaWg2AccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    assert wg.is_permanent_blocked is True
    assert wg.block_reason == "access_expired"
    assert awg2.block_reason is None
    assert awg2.access_until == user.access_until
    assert result["cleared"] >= 1
    assert result["skipped_manual"] >= 1


def test_apply_user_subscription_expiry_blocks_owned(db):
    node = _make_node(db)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    user = User(
        username="owner-expire",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=past.replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user.id,
        client_name="Alice",
        protocols=[VpnType.openvpn, VpnType.wireguard, VpnType.amneziawg2],
    )

    adapter = _adapter()
    with patch("app.services.access_until.get_adapter_for_node", return_value=adapter):
        result = usub.apply_user_subscription_expiry(db, user)

    ovpn = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
    wg = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    awg2 = db.query(AmneziaWg2AccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    assert ovpn.block_reason == "access_expired"
    assert wg.block_reason == "access_expired"
    assert awg2.block_reason == "access_expired"
    assert result["expired"] == 3


def test_apply_user_subscription_expiry_does_not_clobber_concurrent_extension(db):
    node = _make_node(db)
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    future = now + timedelta(days=14)
    user = User(
        username="owner-expire-race",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=past.replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user.id,
        client_name="Alice",
        protocols=[VpnType.openvpn, VpnType.wireguard],
    )
    db.add(
        OpenVpnAccessPolicy(
            node_id=node.id,
            client_name="Alice",
            access_until=past.replace(tzinfo=None),
        )
    )
    db.add(
        WgAccessPolicy(
            node_id=node.id,
            client_name="alice",
            expires_at=past.replace(tzinfo=None),
        )
    )
    db.commit()

    adapter = _adapter()
    with patch("app.services.access_until.get_adapter_for_node", return_value=adapter):
        orig_commit = db.commit
        released = {"done": False}

        def commit_then_concurrent_extend():
            if not released["done"]:
                released["done"] = True
                orig_commit()
                other = sessionmaker(bind=db.get_bind())()
                try:
                    set_access_until(other, "openvpn", node.id, "Alice", future, actor="unlock_codes")
                    set_access_until(other, "wireguard", node.id, "Alice", future, actor="unlock_codes")
                finally:
                    other.close()
                return None
            return orig_commit()

        db.commit = commit_then_concurrent_extend  # type: ignore[method-assign]
        try:
            result = usub.apply_user_subscription_expiry(db, user)
        finally:
            db.commit = orig_commit  # type: ignore[method-assign]

    ovpn = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
    wg = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    assert result["expired"] == 0
    assert result["skipped_not_expired"] == 2
    assert ovpn.access_until == future.replace(tzinfo=None)
    assert wg.expires_at == future.replace(tzinfo=None)
    assert ovpn.block_reason != "access_expired"
    assert wg.block_reason != "access_expired"
