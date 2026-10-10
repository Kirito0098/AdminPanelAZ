"""Portal links: only owner/admin manage them; links die when the creator loses access."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ClientPortalToken, Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.routers import client_portal as portal_router
from app.routers import configs as configs_router
from app.routers import users as users_router
from app.schemas import UserUpdate, VpnConfigUpdate
from app.services import bulk_config_ops
from app.services.client_portal import revoke_creator_portal_links

ADMIN, OWNER, OTHER, ADMIN2 = 1, 2, 3, 4


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    with make() as db:
        db.add_all(
            [
                User(id=ADMIN, username="admin", password_hash="x", role=UserRole.admin, is_active=True),
                User(id=OWNER, username="owner", password_hash="x", role=UserRole.user, is_active=True),
                User(id=OTHER, username="other", password_hash="x", role=UserRole.user, is_active=True),
                User(id=ADMIN2, username="admin2", password_hash="x", role=UserRole.admin, is_active=True),
                Node(id=1, name="local", host="127.0.0.1", is_local=True, status=NodeStatus.online),
            ]
        )
        db.commit()
    try:
        yield make
    finally:
        engine.dispose()


def _config(db, name: str, *, owner_id: int) -> VpnConfig:
    config = VpnConfig(node_id=1, client_name=name, vpn_type=VpnType.wireguard, owner_id=owner_id)
    db.add(config)
    db.commit()
    return config


def _link(db, name: str, token: str, *, creator_id: int) -> None:
    db.add(ClientPortalToken(token=token, node_id=1, client_name=name, created_by_user_id=creator_id))
    db.commit()


def _active_tokens(db) -> set[str]:
    db.expire_all()
    return {row.token for row in db.query(ClientPortalToken).filter(ClientPortalToken.revoked_at.is_(None))}


def test_view_grant_cannot_manage_portal_link(monkeypatch):
    configs = [SimpleNamespace(owner_id=OWNER, client_name="alice")]
    monkeypatch.setattr(portal_router, "_configs_for_client", lambda _db, _name: configs)
    monkeypatch.setattr("app.services.config_access.matches_user_config_grant", lambda *_a: True)

    with pytest.raises(HTTPException) as exc:
        portal_router._assert_can_manage_client(SimpleNamespace(id=OTHER, role=UserRole.user), MagicMock(), "alice")

    assert exc.value.status_code == 403


def test_owner_and_admin_can_manage_portal_link(monkeypatch):
    configs = [SimpleNamespace(owner_id=OWNER, client_name="alice")]
    monkeypatch.setattr(portal_router, "_configs_for_client", lambda _db, _name: configs)

    portal_router._assert_can_manage_client(SimpleNamespace(id=OWNER, role=UserRole.user), MagicMock(), "alice")
    portal_router._assert_can_manage_client(SimpleNamespace(id=ADMIN, role=UserRole.admin), MagicMock(), "alice")


def test_revoke_creator_links_keeps_clients_they_still_own(factory):
    with factory() as db:
        _config(db, "alice", owner_id=OWNER)
        _config(db, "bob", owner_id=OTHER)
        _link(db, "alice", "c_alice", creator_id=OWNER)
        _link(db, "bob", "c_bob", creator_id=OWNER)

        assert revoke_creator_portal_links(db, OWNER) == 1
        db.commit()

        assert _active_tokens(db) == {"c_alice"}


def _stub_update_config(monkeypatch, config) -> None:
    for name in (
        "require_ha_primary_for_client_ops",
        "maybe_replicate_config_metadata",
        "_to_response",
        "_viewer_visibility_policy",
        "resolve_openvpn_group_for_user",
        "_local_ip_for_config",
    ):
        monkeypatch.setattr(configs_router, name, lambda *_a, **_k: None)
    monkeypatch.setattr(configs_router, "get_active_node", lambda _db: SimpleNamespace(id=1, name="local"))
    monkeypatch.setattr(configs_router, "_get_config_for_active_node", lambda _db, _id: config)


def test_update_config_owner_change_revokes_all_client_links(factory, monkeypatch):
    with factory() as db:
        alice = _config(db, "alice", owner_id=OWNER)
        _config(db, "bob", owner_id=OWNER)
        _link(db, "alice", "c_alice", creator_id=ADMIN)
        _link(db, "bob", "c_bob", creator_id=OWNER)
        _stub_update_config(monkeypatch, alice)

        configs_router.update_config(alice.id, VpnConfigUpdate(owner_id=OTHER), db, db.get(User, ADMIN))

        assert _active_tokens(db) == {"c_bob"}


def test_update_config_same_owner_keeps_links(factory, monkeypatch):
    with factory() as db:
        alice = _config(db, "alice", owner_id=OWNER)
        _link(db, "alice", "c_alice", creator_id=ADMIN)
        _stub_update_config(monkeypatch, alice)

        configs_router.update_config(alice.id, VpnConfigUpdate(owner_id=OWNER), db, db.get(User, ADMIN))

        assert _active_tokens(db) == {"c_alice"}


def test_bulk_change_owner_revokes_all_client_links(factory, monkeypatch):
    with factory() as db:
        config_id = _config(db, "alice", owner_id=OWNER).id
        _link(db, "alice", "c_alice", creator_id=ADMIN)
    monkeypatch.setattr(bulk_config_ops, "SessionLocal", factory)
    monkeypatch.setattr(bulk_config_ops, "get_active_adapter", lambda _db: MagicMock())
    monkeypatch.setattr(bulk_config_ops, "get_node_antizapret_path", lambda _db: Path("/tmp"))
    monkeypatch.setattr(bulk_config_ops, "AccessPolicyService", MagicMock())
    monkeypatch.setattr(bulk_config_ops, "maybe_replicate_config_metadata", lambda *_a, **_k: None)

    result = bulk_config_ops._run_single_op(
        operation="change_owner",
        config_id=config_id,
        node_id=1,
        block_days=0,
        renew_cert_days=0,
        owner_id=OTHER,
        actor_username="admin",
    )

    assert result["ok"] is True
    with factory() as db:
        assert _active_tokens(db) == set()


def test_demoted_admin_loses_links_to_foreign_clients(factory, monkeypatch):
    monkeypatch.setattr(users_router.settings, "audit_log_enabled", False)
    with factory() as db:
        _config(db, "alice", owner_id=OWNER)
        _config(db, "dave", owner_id=ADMIN2)
        _link(db, "alice", "c_alice", creator_id=ADMIN2)
        _link(db, "dave", "c_dave", creator_id=ADMIN2)

        users_router.update_user(
            ADMIN2, UserUpdate(role=UserRole.user), MagicMock(), db=db, current_user=db.get(User, ADMIN)
        )

        assert _active_tokens(db) == {"c_dave"}


def _stub_delete_user(monkeypatch) -> None:
    monkeypatch.setattr(users_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(users_router.admin_notify_service, "send_user_delete", lambda *_a, **_k: None)


def test_deleted_user_links_are_revoked(factory, monkeypatch):
    _stub_delete_user(monkeypatch)
    with factory() as db:
        _config(db, "alice", owner_id=OWNER)
        _link(db, "alice", "c_alice", creator_id=OWNER)

        users_router.delete_user(OWNER, MagicMock(), db=db, current_user=db.get(User, ADMIN))

        assert _active_tokens(db) == set()


def test_deleted_admin_links_survive(factory, monkeypatch):
    _stub_delete_user(monkeypatch)
    with factory() as db:
        _config(db, "alice", owner_id=OWNER)
        _config(db, "dave", owner_id=ADMIN2)
        _link(db, "alice", "c_alice", creator_id=ADMIN2)
        _link(db, "dave", "c_dave", creator_id=ADMIN2)

        users_router.delete_user(ADMIN2, MagicMock(), db=db, current_user=db.get(User, ADMIN))

        assert _active_tokens(db) == {"c_alice", "c_dave"}
