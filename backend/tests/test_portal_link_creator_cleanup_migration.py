"""One-shot upgrade cleanup: revoke client portal links whose creator cannot manage the client."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.database import Base
from app.models import AppSetting, ClientPortalToken, Node, NodeStatus, User, UserRole, VpnConfig, VpnType

ADMIN, OWNER, OTHER = 1, 2, 3


@pytest.fixture()
def factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    make = sessionmaker(bind=engine)
    with make() as db:
        db.add_all(
            [
                User(id=ADMIN, username="admin", password_hash="x", role=UserRole.admin, is_active=True),
                User(id=OWNER, username="owner", password_hash="x", role=UserRole.user, is_active=True),
                User(id=OTHER, username="other", password_hash="x", role=UserRole.user, is_active=True),
                Node(id=1, name="local", host="127.0.0.1", is_local=True, status=NodeStatus.online),
            ]
        )
        db.flush()
        for name, owner_id in (("alice", OWNER), ("bob", OTHER), ("carl", OTHER), ("dan", OWNER)):
            db.add(VpnConfig(node_id=1, client_name=name, vpn_type=VpnType.wireguard, owner_id=owner_id))
        db.commit()
    try:
        yield make
    finally:
        engine.dispose()


def _link(db, name: str, token: str, *, creator_id: int | None) -> None:
    db.add(ClientPortalToken(token=token, node_id=1, client_name=name, created_by_user_id=creator_id))
    db.commit()


def _active_tokens(factory) -> set[str]:
    with factory() as db:
        return {row.token for row in db.query(ClientPortalToken).filter(ClientPortalToken.revoked_at.is_(None))}


def test_cleanup_revokes_links_whose_creator_cannot_manage_the_client(factory):
    with factory() as db:
        _link(db, "alice", "c_owner_own", creator_id=OWNER)
        _link(db, "bob", "c_owner_view_only", creator_id=OWNER)
        _link(db, "carl", "c_admin_foreign", creator_id=ADMIN)
        _link(db, "dan", "c_no_creator", creator_id=None)
        _link(db, "ghost", "c_admin_orphan", creator_id=ADMIN)

    database._migrate_revoke_unmanaged_client_portal_links()

    assert _active_tokens(factory) == {"c_owner_own", "c_admin_foreign", "c_no_creator"}


def test_cleanup_runs_once(factory):
    with factory() as db:
        _link(db, "bob", "c_first", creator_id=OWNER)

    database._migrate_revoke_unmanaged_client_portal_links()

    with factory() as db:
        _link(db, "bob", "c_after_upgrade", creator_id=OWNER)
        marker = db.query(AppSetting).filter(AppSetting.key == database._PORTAL_LINK_CREATOR_CLEANUP_MARKER).one()
        assert marker.value == "1"

    database._migrate_revoke_unmanaged_client_portal_links()

    assert _active_tokens(factory) == {"c_after_upgrade"}
