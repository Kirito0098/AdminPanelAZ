from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserRole, VpnConfig, VpnType
from app.schemas import UserFromExistingCreate
from app.services import config_ownership


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _admin(db) -> User:
    u = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_assign_rejects_ha_shadow(db):
    admin = _admin(db)
    primary = VpnConfig(
        node_id=1, client_name="alice", vpn_type=VpnType.wireguard, owner_id=admin.id
    )
    db.add(primary)
    db.commit()
    db.refresh(primary)
    shadow = VpnConfig(
        node_id=2,
        client_name="alice",
        vpn_type=VpnType.wireguard,
        owner_id=admin.id,
        ha_primary_config_id=primary.id,
    )
    db.add(shadow)
    db.commit()
    db.refresh(shadow)
    new_owner = User(username="bob", password_hash="x", role=UserRole.user, is_active=True)
    db.add(new_owner)
    db.commit()
    db.refresh(new_owner)
    with pytest.raises(ValueError, match="primary"):
        config_ownership.assign_config_owner(db, config=shadow, new_owner=new_owner)


def test_create_from_existing_assigns_primaries(db, monkeypatch):
    """Exercise the router helper path if extracted; else call service used by endpoint."""
    admin = _admin(db)
    c1 = VpnConfig(node_id=1, client_name="a", vpn_type=VpnType.openvpn, owner_id=admin.id)
    # owner_id is NOT NULL on VpnConfig; use admin as prior owner (same as c1).
    c2 = VpnConfig(node_id=1, client_name="b", vpn_type=VpnType.wireguard, owner_id=admin.id)
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    monkeypatch.setattr(config_ownership, "revoke_client_portal_links", lambda *a, **k: 0)
    monkeypatch.setattr(config_ownership, "maybe_replicate_config_metadata", lambda *a, **k: None)

    user = config_ownership.create_user_from_existing(
        db,
        payload=UserFromExistingCreate(
            username="subscriber",
            panel_login_enabled=False,
            password=None,
            access_until=datetime(2030, 1, 1, tzinfo=timezone.utc),
            config_ids=[c1.id, c2.id],
            config_quota=5,
        ),
        actor=admin,
    )
    db.refresh(c1)
    db.refresh(c2)
    assert user.username == "subscriber"
    assert user.role == UserRole.user
    assert user.client_base_name is None
    assert user.access_until is not None
    assert c1.owner_id == user.id
    assert c2.owner_id == user.id


def test_create_from_existing_config_quota_zero_unlimited(db, monkeypatch):
    admin = _admin(db)
    cfg = VpnConfig(node_id=1, client_name="a", vpn_type=VpnType.openvpn, owner_id=admin.id)
    db.add(cfg)
    db.commit()
    db.refresh(cfg)

    monkeypatch.setattr(config_ownership, "revoke_client_portal_links", lambda *a, **k: 0)
    monkeypatch.setattr(config_ownership, "maybe_replicate_config_metadata", lambda *a, **k: None)

    user = config_ownership.create_user_from_existing(
        db,
        payload=UserFromExistingCreate(
            username="unlimited",
            panel_login_enabled=False,
            config_ids=[cfg.id],
            config_quota=0,
        ),
        actor=admin,
    )
    db.refresh(cfg)
    assert cfg.owner_id == user.id


def test_create_from_existing_pending_deletion_returns_409(db, monkeypatch):
    from app.services import user_identity_conflict

    admin = _admin(db)
    ghost = User(
        username="subscriber",
        password_hash="x",
        role=UserRole.user,
        provision_state="pending_deletion",
    )
    db.add(ghost)
    db.commit()
    ghost_id = ghost.id

    enqueued: list[tuple[int, str]] = []
    monkeypatch.setattr(
        user_identity_conflict,
        "enqueue_user_delete_cleanup",
        lambda _db, *, user_id, actor_username: enqueued.append((user_id, actor_username)),
    )

    with pytest.raises(HTTPException) as excinfo:
        config_ownership.create_user_from_existing(
            db,
            payload=UserFromExistingCreate(
                username="subscriber",
                panel_login_enabled=False,
                config_ids=[],
            ),
            actor=admin,
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == "user_deletion_pending"
    assert enqueued == [(ghost_id, "admin")]
