"""Client portal links die with the last VpnConfig row of the client."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ClientPortalToken, Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.routers import configs as configs_router
from app.services import awg2_expire_worker, bulk_config_ops
from app.services import client_portal
from app.services.client_portal import cleanup_deleted_client_records, get_or_create_portal_token
from app.services.config_import import _remove_stale_configs


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    with make() as db:
        db.add(User(id=1, username="admin", password_hash="x", role=UserRole.admin, is_active=True))
        db.add(Node(id=1, name="local", host="127.0.0.1", is_local=True, status=NodeStatus.online))
        db.commit()
    try:
        yield make
    finally:
        engine.dispose()


def _config(db, name: str, vpn_type: VpnType = VpnType.wireguard) -> VpnConfig:
    config = VpnConfig(node_id=1, client_name=name, vpn_type=vpn_type, owner_id=1)
    db.add(config)
    db.commit()
    return config


def _link(db, name: str, token: str) -> None:
    db.add(ClientPortalToken(token=token, node_id=1, client_name=name, created_by_user_id=1))
    db.commit()


def _active_links(db, name: str) -> list[str]:
    return [
        row.token
        for row in db.query(ClientPortalToken).filter(
            ClientPortalToken.client_name == name,
            ClientPortalToken.revoked_at.is_(None),
        )
    ]


def test_link_revoked_when_last_config_deleted(factory):
    with factory() as db:
        config = _config(db, "alice")
        _link(db, "alice", "c_alice")

        db.delete(config)
        cleanup_deleted_client_records(db, config)
        db.commit()

        assert _active_links(db, "alice") == []


def test_link_kept_while_other_protocol_remains(factory):
    with factory() as db:
        wireguard = _config(db, "alice", VpnType.wireguard)
        _config(db, "alice", VpnType.openvpn)
        _link(db, "alice", "c_alice")

        db.delete(wireguard)
        cleanup_deleted_client_records(db, wireguard)
        db.commit()

        assert _active_links(db, "alice") == ["c_alice"]


def test_recreated_client_gets_new_link(factory, monkeypatch):
    monkeypatch.setattr(client_portal, "_portal_node_id", lambda _db: 1)
    with factory() as db:
        config = _config(db, "alice")
        _link(db, "alice", "c_old")
        db.delete(config)
        cleanup_deleted_client_records(db, config)
        db.commit()

        _config(db, "alice")
        row = get_or_create_portal_token(db, client_name="alice")

        assert row.token != "c_old"
        assert _active_links(db, "alice") == [row.token]


def test_delete_config_route_revokes_link(factory, monkeypatch):
    monkeypatch.setattr(configs_router, "require_ha_primary_for_client_ops", lambda _db: None)
    monkeypatch.setattr(configs_router, "get_active_adapter", lambda _db: MagicMock())
    monkeypatch.setattr(configs_router, "get_active_node", lambda _db: SimpleNamespace(id=1, name="local"))
    monkeypatch.setattr(configs_router.admin_notify_service, "send_config_delete", lambda *_a, **_k: None)
    monkeypatch.setattr(configs_router, "get_client_timezone_from_request", lambda _r: "UTC")
    with factory() as db:
        config = _config(db, "alice")
        _link(db, "alice", "c_alice")
        monkeypatch.setattr(configs_router, "_get_config_for_active_node", lambda _db, _id: config)

        configs_router.delete_config(config.id, MagicMock(), db, db.get(User, 1))

        assert _active_links(db, "alice") == []


def test_bulk_delete_revokes_link(factory, monkeypatch):
    with factory() as db:
        config_id = _config(db, "alice").id
        _link(db, "alice", "c_alice")
    monkeypatch.setattr(bulk_config_ops, "SessionLocal", factory)
    monkeypatch.setattr(bulk_config_ops, "get_active_adapter", lambda _db: MagicMock())
    monkeypatch.setattr(bulk_config_ops, "get_node_antizapret_path", lambda _db: Path("/tmp"))
    monkeypatch.setattr(bulk_config_ops, "AccessPolicyService", MagicMock())
    monkeypatch.setattr(bulk_config_ops, "get_active_node", lambda _db: SimpleNamespace(id=1, name="local"))
    monkeypatch.setattr(bulk_config_ops.admin_notify_service, "send_config_delete", lambda *_a, **_k: None)

    result = bulk_config_ops._run_single_op(
        operation="delete",
        config_id=config_id,
        node_id=1,
        block_days=0,
        renew_cert_days=0,
        owner_id=None,
        actor_username="admin",
    )

    assert result["ok"] is True
    with factory() as db:
        assert _active_links(db, "alice") == []


def test_awg2_expire_delete_revokes_link(factory):
    with factory() as db:
        config = _config(db, "alice", VpnType.amneziawg2)
        _link(db, "alice", "c_alice")

        awg2_expire_worker._delete_config_row(db, db.get(Node, 1), config)
        db.commit()

        assert _active_links(db, "alice") == []


def test_config_import_stale_removal_revokes_link(factory):
    with factory() as db:
        _config(db, "alice")
        _link(db, "alice", "c_alice")

        assert _remove_stale_configs(db, 1, set(), set(), set()) == 1
        db.commit()

        assert _active_links(db, "alice") == []
