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
        updated, _cascade = usub.set_user_access_until(db, user, future, actor="admin")

    assert usub.get_user_access_until(updated) == future
    ovpn = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
    wg = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    assert ovpn.access_until == future.replace(tzinfo=None)
    assert wg.expires_at == future.replace(tzinfo=None)


def test_set_user_access_until_commit_false_defers_reconcile(db):
    node = _make_node(db)
    future = datetime.now(timezone.utc) + timedelta(days=14)
    user = User(username="owner-sync-deferred", password_hash="x", role=UserRole.user, is_active=True)
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

    with patch("app.services.user_subscription._reconcile_access_until") as reconcile:
        updated, _cascade = usub.set_user_access_until(db, user, future, actor="admin", commit=False)

    assert usub.get_user_access_until(updated) == future
    assert reconcile.call_count == 0
    ovpn = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
    wg = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    assert ovpn.access_until == future.replace(tzinfo=None)
    assert wg.expires_at == future.replace(tzinfo=None)


def test_client_access_conflicts_with_owner_compares_normalized_deadlines(db):
    future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    owner = User(
        username="owner-conflict",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=future.replace(tzinfo=None),
    )
    db.add(owner)
    db.commit()

    assert usub.client_access_conflicts_with_owner(db, owner=owner, client_access_until=future) is False
    assert usub.client_access_conflicts_with_owner(
        db,
        owner=owner,
        client_access_until=future + timedelta(days=1),
    ) is True
    assert usub.client_access_conflicts_with_owner(db, owner=owner, client_access_until=None) is True


def test_client_access_conflicts_with_owner_unset_allows_any_client_deadline(db):
    future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    owner = User(
        username="owner-no-deadline",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=None,
    )
    db.add(owner)
    db.commit()

    assert usub.client_access_conflicts_with_owner(db, owner=owner, client_access_until=None) is False
    assert usub.client_access_conflicts_with_owner(db, owner=owner, client_access_until=future) is False


def test_sync_client_access_until_from_owner_updates_only_requested_client(db):
    node = _make_node(db)
    future = datetime.now(timezone.utc) + timedelta(days=21)
    other = datetime.now(timezone.utc) + timedelta(days=3)
    owner = User(
        username="owner-single-sync",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=future.replace(tzinfo=None),
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=owner.id,
        client_name="Alice",
        protocols=[VpnType.openvpn, VpnType.wireguard],
    )
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=owner.id,
        client_name="Bob",
        protocols=[VpnType.openvpn],
    )

    with patch("app.services.access_until.get_adapter_for_node", return_value=_adapter()):
        set_access_until(db, "openvpn", node.id, "Alice", other, actor="admin")
        set_access_until(db, "wireguard", node.id, "Alice", other, actor="admin")
        set_access_until(db, "openvpn", node.id, "Bob", other, actor="admin")
        result = usub.sync_client_access_until_from_owner(
            db,
            owner=owner,
            node_id=node.id,
            client_name="Alice",
            actor="admin",
        )

    alice_ovpn = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
    alice_wg = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    bob_ovpn = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Bob").one()
    assert result["targets"] == 2
    assert result["synced"] == 2
    assert alice_ovpn.access_until == future.replace(tzinfo=None)
    assert alice_wg.expires_at == future.replace(tzinfo=None)
    assert bob_ovpn.access_until == other.replace(tzinfo=None)


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


def test_apply_due_user_subscription_blocks_cascades(db):
    node = _make_node(db)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    future = datetime.now(timezone.utc) + timedelta(days=14)

    expired_user = User(
        username="owner-expired-due",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=past.replace(tzinfo=None),
    )
    active_user = User(
        username="owner-active-due",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=future.replace(tzinfo=None),
    )
    db.add_all([expired_user, active_user])
    db.commit()
    db.refresh(expired_user)
    db.refresh(active_user)

    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=expired_user.id,
        client_name="Alice",
        protocols=[VpnType.openvpn, VpnType.wireguard],
    )
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=active_user.id,
        client_name="Bob",
        protocols=[VpnType.openvpn],
    )

    adapter = _adapter()
    with patch("app.services.access_until.get_adapter_for_node", return_value=adapter):
        result = usub.apply_due_user_subscription_blocks(db)

    expired_ovpn = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").one()
    expired_wg = db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").one()
    assert expired_ovpn.block_reason == "access_expired"
    assert expired_wg.block_reason == "access_expired"
    assert result == {
        "users_due": 1,
        "cascaded": 2,
        "skipped": 0,
        "errors": 0,
    }


def test_apply_due_user_subscription_blocks_rechecks_user_after_snapshot_release(db):
    node = _make_node(db)
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    future = now + timedelta(days=14)

    user = User(
        username="owner-due-race",
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

    orig_commit = db.commit
    released = {"done": False}

    def commit_then_extend_user():
        if not released["done"]:
            released["done"] = True
            orig_commit()
            other = sessionmaker(bind=db.get_bind())()
            try:
                fresh_user = other.get(User, user.id)
                usub.set_user_access_until(other, fresh_user, future, actor="admin", sync_clients=False)
            finally:
                other.close()
            return None
        return orig_commit()

    db.commit = commit_then_extend_user  # type: ignore[method-assign]
    try:
        with patch("app.services.access_until.get_adapter_for_node", return_value=_adapter()):
            result = usub.apply_due_user_subscription_blocks(db)
    finally:
        db.commit = orig_commit  # type: ignore[method-assign]

    db.refresh(user)
    assert user.access_until == future.replace(tzinfo=None)
    assert db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Alice").count() == 0
    assert db.query(WgAccessPolicy).filter_by(node_id=node.id, client_name="alice").count() == 0
    assert result == {
        "users_due": 1,
        "cascaded": 0,
        "skipped": 1,
        "errors": 0,
    }


def test_migrate_user_access_until_backfill_sets_max_of_owned_clients(db, monkeypatch):
    from app import database

    test_engine = db.get_bind()
    monkeypatch.setattr(database, "engine", test_engine)

    node = _make_node(db)
    sooner = datetime.now(timezone.utc) + timedelta(days=7)
    later = datetime.now(timezone.utc) + timedelta(days=30)
    user = User(username="backfill-owner", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user.id,
        client_name="Alice",
        protocols=[VpnType.openvpn],
    )
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user.id,
        client_name="Bob",
        protocols=[VpnType.wireguard],
    )
    db.add(
        OpenVpnAccessPolicy(
            node_id=node.id,
            client_name="Alice",
            access_until=sooner.replace(tzinfo=None),
        )
    )
    db.add(
        WgAccessPolicy(
            node_id=node.id,
            client_name="bob",
            expires_at=later.replace(tzinfo=None),
        )
    )
    db.commit()

    database._migrate_user_access_until_backfill()

    db.refresh(user)
    assert user.access_until == later.replace(tzinfo=None)


@pytest.mark.parametrize(
    "unlimited",
    ["no_policy_row", "null_deadline", "other_protocol_of_limited_client"],
)
def test_migrate_user_access_until_backfill_skips_owner_with_unlimited_client(db, monkeypatch, unlimited):
    from app import database

    monkeypatch.setattr(database, "engine", db.get_bind())
    node = _make_node(db)
    later = datetime.now(timezone.utc) + timedelta(days=30)
    user = User(username="backfill-mixed", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()

    _make_owned_client(db, node_id=node.id, owner_id=user.id, client_name="Alice", protocols=[VpnType.openvpn])
    db.add(OpenVpnAccessPolicy(node_id=node.id, client_name="Alice", access_until=later.replace(tzinfo=None)))
    if unlimited == "other_protocol_of_limited_client":
        _make_owned_client(db, node_id=node.id, owner_id=user.id, client_name="Alice", protocols=[VpnType.wireguard])
    else:
        _make_owned_client(db, node_id=node.id, owner_id=user.id, client_name="Bob", protocols=[VpnType.openvpn])
        if unlimited == "null_deadline":
            db.add(OpenVpnAccessPolicy(node_id=node.id, client_name="Bob", access_until=None))
    db.commit()

    database._migrate_user_access_until_backfill()

    db.refresh(user)
    # Подписка ограничила бы и бессрочного клиента: при её окончании его блокирует apply_user_subscription_expiry.
    assert user.access_until is None


def test_migrate_user_access_until_backfill_skips_owner_with_only_expired_clients(db, monkeypatch):
    from app import database

    monkeypatch.setattr(database, "engine", db.get_bind())
    node = _make_node(db)
    user = User(username="backfill-expired", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()
    _make_owned_client(db, node_id=node.id, owner_id=user.id, client_name="Alice", protocols=[VpnType.openvpn])
    past = datetime.now(timezone.utc) - timedelta(days=3)
    db.add(OpenVpnAccessPolicy(node_id=node.id, client_name="Alice", access_until=past.replace(tzinfo=None)))
    db.commit()

    database._migrate_user_access_until_backfill()

    db.refresh(user)
    assert user.access_until is None


def test_migrate_user_access_until_backfill_idempotent_and_skips_non_null(db, monkeypatch):
    from app import database

    test_engine = db.get_bind()
    monkeypatch.setattr(database, "engine", test_engine)

    node = _make_node(db)
    later = datetime.now(timezone.utc) + timedelta(days=30)
    preset = datetime.now(timezone.utc) + timedelta(days=3)
    user_null = User(username="backfill-null", password_hash="x", role=UserRole.user, is_active=True)
    user_set = User(
        username="backfill-set",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=preset.replace(tzinfo=None),
    )
    db.add_all([user_null, user_set])
    db.commit()
    db.refresh(user_null)
    db.refresh(user_set)

    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user_null.id,
        client_name="Alice",
        protocols=[VpnType.openvpn],
    )
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user_set.id,
        client_name="Bob",
        protocols=[VpnType.openvpn],
    )
    db.add(
        OpenVpnAccessPolicy(
            node_id=node.id,
            client_name="Alice",
            access_until=later.replace(tzinfo=None),
        )
    )
    db.add(
        OpenVpnAccessPolicy(
            node_id=node.id,
            client_name="Bob",
            access_until=later.replace(tzinfo=None),
        )
    )
    db.commit()

    database._migrate_user_access_until_backfill()
    db.refresh(user_null)
    db.refresh(user_set)
    assert user_null.access_until == later.replace(tzinfo=None)
    assert user_set.access_until == preset.replace(tzinfo=None)

    database._migrate_user_access_until_backfill()
    db.refresh(user_null)
    assert user_null.access_until == later.replace(tzinfo=None)


def test_migrate_user_access_until_backfill_runs_once_per_db(db, monkeypatch):
    """A client deadline appearing after the backfill must not invent a subscription."""
    from app import database

    test_engine = db.get_bind()
    monkeypatch.setattr(database, "engine", test_engine)

    node = _make_node(db)
    user = User(username="backfill-once", password_hash="x", role=UserRole.user, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user.id,
        client_name="Alice",
        protocols=[VpnType.openvpn],
    )

    database._migrate_user_access_until_backfill()
    db.refresh(user)
    assert user.access_until is None

    # Admin confirms a divergent client deadline (or the owner changes) — the
    # next panel restart must not adopt it as the owner's subscription.
    past = datetime.now(timezone.utc) - timedelta(days=5)
    db.add(
        OpenVpnAccessPolicy(
            node_id=node.id,
            client_name="Alice",
            access_until=past.replace(tzinfo=None),
        )
    )
    db.commit()

    database._migrate_user_access_until_backfill()
    db.refresh(user)
    assert user.access_until is None


def test_apply_owner_access_until_to_config_inherits_deadline(db):
    node = _make_node(db)
    future = datetime.now(timezone.utc) + timedelta(days=21)
    owner = User(
        username="owner-inherit",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=future.replace(tzinfo=None),
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    config = VpnConfig(
        node_id=node.id,
        client_name="NewGuy",
        vpn_type=VpnType.openvpn,
        owner_id=owner.id,
        cert_expire_days=3650,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    with patch("app.services.access_until.get_adapter_for_node", return_value=_adapter()):
        with patch("app.services.user_subscription._replicate_access_until_queue", return_value=[]) as replicate:
            result = usub.apply_owner_access_until_to_config(db, config, actor="admin")

    assert result["applied"] is True
    row = db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="NewGuy").one()
    assert row.access_until == future.replace(tzinfo=None)
    assert replicate.called


def test_apply_owner_access_until_skips_unlimited_owner(db):
    node = _make_node(db)
    owner = User(username="owner-unlimited", password_hash="x", role=UserRole.user, is_active=True)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    config = VpnConfig(
        node_id=node.id,
        client_name="Free",
        vpn_type=VpnType.openvpn,
        owner_id=owner.id,
        cert_expire_days=3650,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    result = usub.apply_owner_access_until_to_config(db, config, actor="admin")
    assert result == {"applied": False, "reason": "owner_unlimited"}
    assert db.query(OpenVpnAccessPolicy).filter_by(node_id=node.id, client_name="Free").count() == 0


def test_sync_owned_clients_replicates_ha(db):
    node = _make_node(db)
    future = datetime.now(timezone.utc) + timedelta(days=10)
    user = User(
        username="owner-ha",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        access_until=future.replace(tzinfo=None),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _make_owned_client(
        db,
        node_id=node.id,
        owner_id=user.id,
        client_name="Alice",
        protocols=[VpnType.openvpn],
    )

    with patch("app.services.access_until.get_adapter_for_node", return_value=_adapter()):
        with patch(
            "app.services.node_sync.policy_sync.maybe_replicate_policy_op",
            return_value=None,
        ) as replicate:
            result = usub.sync_owned_clients_access_until(db, user, actor="admin")

    assert result["synced"] == 1
    assert result["replicate_errors"] == []
    replicate.assert_called()
    kwargs = replicate.call_args.kwargs
    assert kwargs["op"] == "set_access_until"
    assert kwargs["client_name"] == "Alice"
    assert kwargs["vpn_type"] == VpnType.openvpn


def test_reconcile_queue_isolates_errors(db):
    node = _make_node(db)
    calls = {"n": 0}

    def boom(service, protocol, client_name):
        calls["n"] += 1
        if client_name == "bad":
            raise RuntimeError("node offline")

    with patch("app.services.user_subscription._policy_service_for_node", return_value=object()):
        with patch("app.services.user_subscription._reconcile_access_until", side_effect=boom):
            result = usub._reconcile_owned_client_queue(
                db,
                [
                    (node.id, "openvpn", "good"),
                    (node.id, "openvpn", "bad"),
                    (node.id, "openvpn", "also-good"),
                ],
            )

    assert result["synced"] == 2
    assert len(result["errors"]) == 1
    assert result["errors"][0]["client_name"] == "bad"
    assert "offline" in result["errors"][0]["error"]
    assert calls["n"] == 3
