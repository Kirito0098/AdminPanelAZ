"""Per-device OpenVPN disconnect: session id only, no cooldown, no policy replication."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole
from app.routers import client_access as access_router


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    session = make()
    session.add(Node(id=1, name="1Cent-EE", host="h", is_local=True, status=NodeStatus.online))
    session.add(User(id=1, username="admin", password_hash="x", role=UserRole.admin, is_active=True))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _payload(
    profile: str = "antizapret-udp",
    client_id: int = 1041,
    node_id: int | None = None,
    client_name: str | None = None,
    block_minutes: int | None = None,
):
    return access_router.OpenVpnSessionDisconnectRequest(
        profile=profile,
        client_id=client_id,
        node_id=node_id,
        client_name=client_name,
        block_minutes=block_minutes,
    )


def _admin(db):
    return db.get(User, 1)


def test_disconnect_session_kills_one_device(db, monkeypatch):
    adapter = SimpleNamespace(kill_openvpn_session=MagicMock(return_value={"success": True, "client_id": 1041}))
    monkeypatch.setattr(access_router, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(access_router, "log_action", lambda *_a, **_k: None)

    result = access_router.openvpn_disconnect_session(_payload(), MagicMock(), db=db, user=_admin(db))

    assert result["success"] is True
    adapter.kill_openvpn_session.assert_called_once_with("antizapret-udp", 1041)


def test_disconnect_session_reports_the_openvpn_error(db, monkeypatch):
    adapter = SimpleNamespace(
        kill_openvpn_session=MagicMock(
            return_value={"success": False, "message": "ERROR: client-kill command failed"}
        )
    )
    monkeypatch.setattr(access_router, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(access_router, "log_action", lambda *_a, **_k: None)

    with pytest.raises(HTTPException) as excinfo:
        access_router.openvpn_disconnect_session(_payload(), MagicMock(), db=db, user=_admin(db))

    assert excinfo.value.status_code == 404
    assert "client-kill" in str(excinfo.value.detail)


def test_disconnect_session_rejects_unknown_node(db):
    with pytest.raises(HTTPException) as excinfo:
        access_router.openvpn_disconnect_session(
            _payload(node_id=999), MagicMock(), db=db, user=_admin(db)
        )

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Узел не найден"


def test_disconnect_session_with_block_sets_a_temp_block(db, monkeypatch):
    adapter = SimpleNamespace(kill_openvpn_session=MagicMock(return_value={"success": True}))
    monkeypatch.setattr(access_router, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(access_router, "log_action", lambda *_a, **_k: None)
    blocks: list[tuple] = []
    monkeypatch.setattr(access_router, "_apply_openvpn_temp_block", lambda *args: blocks.append(args))

    result = access_router.openvpn_disconnect_session(
        _payload(client_name="bob", block_minutes=15), MagicMock(), db=db, user=_admin(db)
    )

    assert result["block_minutes"] == 15
    assert len(blocks) == 1
    assert blocks[0][2:] == ("bob", 15, "admin")


def test_disconnect_session_refuses_to_block_without_a_client_name(db, monkeypatch):
    adapter = SimpleNamespace(kill_openvpn_session=MagicMock(return_value={"success": True}))
    monkeypatch.setattr(access_router, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(access_router, "log_action", lambda *_a, **_k: None)

    with pytest.raises(HTTPException) as excinfo:
        access_router.openvpn_disconnect_session(
            _payload(block_minutes=15), MagicMock(), db=db, user=_admin(db)
        )

    assert excinfo.value.status_code == 400
    adapter.kill_openvpn_session.assert_not_called()
