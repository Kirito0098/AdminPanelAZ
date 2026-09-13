"""API tests for node transport list + PATCH."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base
from app.models import Node, NodeStatus
from app.schemas import NodeTransportUpdate
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.ssh_tunnel_pool import EnsureResult


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()



def _ok_preflight(current: str = "http", wanted: str = "http"):
    return SimpleNamespace(
        ok=True,
        current=current,
        wanted=wanted,
        message="ok",
        hint=None,
        probe_status="online",
        probe_error=None,
        http_status=200,
    )


def _allow_preflight(monkeypatch, nodes_router, *, current: str = "http", wanted: str = "http"):
    monkeypatch.setattr(
        nodes_router,
        "preflight_transport_switch",
        lambda _db, _node, body: _ok_preflight(
            current=current,
            wanted=(body.transport or wanted),
        ),
    )

def _add_node(db, *, name: str = "n1", kind: str = "vpn", transport: str = "http") -> Node:
    node = Node(
        name=name,
        host="10.0.0.1",
        port=9100 if kind == "vpn" else 9101,
        api_key_hash="hash",
        api_key_encrypted="enc",
        is_local=False,
        transport=transport,
        mtls_enabled=(transport == "mtls"),
        node_kind=kind,
        status=NodeStatus.unknown,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def test_list_node_transports(monkeypatch):
    from app.routers import nodes as nodes_router
    from app.services import node_transport as nt

    monkeypatch.setattr(nt, "is_node_ssh_transport_enabled", lambda _db=None: False)
    resp = nodes_router.list_node_transports(SimpleNamespace())
    ids = [i.id for i in resp.items]
    assert ids == ["http", "mtls", "ssh"]
    by_id = {i.id: i for i in resp.items}
    assert by_id["ssh"].available is False
    assert by_id["http"].available is True


def test_list_transports_ssh_available_follows_toggle(monkeypatch):
    from app.routers import nodes as nodes_router
    from app.services import node_transport as nt

    monkeypatch.setattr(nt, "is_node_ssh_transport_enabled", lambda _db=None: False)
    resp = nodes_router.list_node_transports(SimpleNamespace())
    assert {item.id: item.available for item in resp.items}["ssh"] is False

    monkeypatch.setattr(nt, "is_node_ssh_transport_enabled", lambda _db=None: True)
    resp = nodes_router.list_node_transports(SimpleNamespace())
    assert {item.id: item.available for item in resp.items}["ssh"] is True


def test_patch_ssh_rejected_when_toggle_off(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.services import node_transport_preflight as pf

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "is_node_ssh_transport_enabled", lambda _db: False)
    monkeypatch.setattr(pf, "is_node_ssh_transport_enabled", lambda _db=None: False)
    node = _add_node(db, transport="http")
    admin = SimpleNamespace(id=1, username="admin")

    with pytest.raises(HTTPException) as exc:
        nodes_router.patch_node_transport(
            node.id,
            NodeTransportUpdate(
                transport="ssh",
                ssh_host="8.8.8.8",
                ssh_username="root",
                ssh_private_key="PRIVATE KEY",
            ),
            admin=admin,
            db=db,
        )
    assert exc.value.status_code == 403
    assert "SSH transport узлов" in str(exc.value.detail)

    db.refresh(node)
    assert node.transport == "http"
    assert node.mtls_enabled is False


def test_patch_ssh_requires_key_when_not_configured(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.services import node_transport_preflight as pf

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "is_node_ssh_transport_enabled", lambda _db: True)
    monkeypatch.setattr(pf, "is_node_ssh_transport_enabled", lambda _db=None: True)
    node = _add_node(db, transport="http")
    admin = SimpleNamespace(id=1, username="admin")

    with pytest.raises(HTTPException) as exc:
        nodes_router.patch_node_transport(
            node.id,
            NodeTransportUpdate(
                transport="ssh",
                ssh_host="8.8.8.8",
                ssh_username="root",
            ),
            admin=admin,
            db=db,
        )
    assert exc.value.status_code == 400
    assert "приватный ключ" in str(exc.value.detail)


def test_patch_ssh_stores_encrypted_key_not_in_response(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    _allow_preflight(monkeypatch, nodes_router, current="http", wanted="ssh")
    monkeypatch.setattr(nodes_router, "is_node_ssh_transport_enabled", lambda _db: True)
    pool = MagicMock()
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: pool)
    node = _add_node(db, transport="http")
    admin = SimpleNamespace(id=1, username="admin")
    private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc123\n-----END OPENSSH PRIVATE KEY-----"
    passphrase = "secret-passphrase"

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(
            transport="ssh",
            ssh_host="8.8.8.8",
            ssh_port=2222,
            ssh_username="root",
            ssh_private_key=private_key,
            ssh_passphrase=passphrase,
            ssh_remote_agent_host="127.0.0.1",
        ),
        admin=admin,
        db=db,
    )

    assert resp.transport == "ssh"
    assert resp.mtls_enabled is False
    assert resp.ssh_host == "8.8.8.8"
    assert resp.ssh_port == 2222
    assert resp.ssh_username == "root"
    assert resp.ssh_key_configured is True
    assert "ssh_private_key" not in resp.model_dump()
    assert "ssh_passphrase" not in resp.model_dump()

    db.refresh(node)
    assert node.transport == "ssh"
    assert node.ssh_private_key_encrypted
    assert node.ssh_private_key_encrypted != private_key
    assert decrypt_secret(node.ssh_private_key_encrypted, get_settings().secret_key) == private_key
    assert decrypt_secret(node.ssh_passphrase_encrypted, get_settings().secret_key) == passphrase
    pool.drop.assert_called_once_with(node.id)


def test_patch_ssh_blank_passphrase_keeps_existing_secret(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    _allow_preflight(monkeypatch, nodes_router, current="http", wanted="ssh")
    monkeypatch.setattr(nodes_router, "is_node_ssh_transport_enabled", lambda _db: True)
    pool = MagicMock()
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: pool)
    existing_passphrase = "existing-secret"
    node = _add_node(db, transport="ssh")
    node.ssh_host = "8.8.8.8"
    node.ssh_username = "root"
    node.ssh_private_key_encrypted = "enc-key"
    node.ssh_passphrase_encrypted = encrypt_secret(existing_passphrase, get_settings().secret_key)
    db.add(node)
    db.commit()
    db.refresh(node)
    admin = SimpleNamespace(id=1, username="admin")

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(
            transport="ssh",
            ssh_host="8.8.8.8",
            ssh_username="root",
            ssh_passphrase="   ",
        ),
        admin=admin,
        db=db,
    )

    assert resp.transport == "ssh"
    db.refresh(node)
    assert decrypt_secret(node.ssh_passphrase_encrypted, get_settings().secret_key) == existing_passphrase
    pool.drop.assert_called_once_with(node.id)


def test_patch_transport_proxy_http_to_mtls(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    _allow_preflight(monkeypatch, nodes_router, current="http", wanted="mtls")
    node = _add_node(db, kind="proxy", transport="http")
    admin = SimpleNamespace(id=1, username="admin")

    def _fake_enable(db_session, n, actor):
        n.transport = "mtls"
        n.mtls_enabled = True
        db_session.add(n)
        db_session.commit()
        db_session.refresh(n)
        return n

    monkeypatch.setattr(nodes_router, "enable_mtls", _fake_enable)

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(transport="mtls"),
        admin=admin,
        db=db,
    )
    assert resp.transport == "mtls"
    assert resp.mtls_enabled is True
    db.refresh(node)
    assert node.transport == "mtls"


def test_patch_transport_noop_same_value(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db, transport="http")
    admin = SimpleNamespace(id=1, username="admin")
    enable = MagicMock()
    monkeypatch.setattr(nodes_router, "enable_mtls", enable)

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(transport="http"),
        admin=admin,
        db=db,
    )
    assert resp.transport == "http"
    enable.assert_not_called()


def test_patch_transport_drops_ssh_tunnel_when_switching_to_http(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    _allow_preflight(monkeypatch, nodes_router, current="ssh", wanted="http")
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")
    pool = MagicMock()
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: pool)

    def _fake_disable(db_session, n, actor):
        n.transport = "http"
        n.mtls_enabled = False
        db_session.add(n)
        db_session.commit()
        db_session.refresh(n)
        return n

    monkeypatch.setattr(nodes_router, "disable_mtls", _fake_disable)

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(transport="http"),
        admin=admin,
        db=db,
    )
    assert resp.transport == "http"
    pool.drop.assert_called_once_with(node.id)


def test_patch_transport_local_rejected(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db)
    node.is_local = True
    db.add(node)
    db.commit()
    admin = SimpleNamespace(id=1, username="admin")

    with pytest.raises(HTTPException) as exc:
        nodes_router.patch_node_transport(
            node.id,
            NodeTransportUpdate(transport="mtls"),
            admin=admin,
            db=db,
        )
    assert exc.value.status_code == 400


def test_remote_http_endpoint_persists_discovered_host_key_on_caller_thread(db, monkeypatch):
    from app.services import node_manager

    node = _add_node(db, transport="ssh")
    node.node_metadata = "{}"
    db.add(node)
    db.commit()
    db.refresh(node)

    class _Pool:
        def ensure(self, _node):
            return EnsureResult(
                local_port=45123,
                discovered_host_key_text="ssh-ed25519 AAAAC3NzaPersisted",
            )

    monkeypatch.setattr("app.services.ssh_tunnel_pool.get_ssh_tunnel_pool", lambda: _Pool())

    host, port, uses_tls = node_manager._remote_http_endpoint(node)

    assert (host, port, uses_tls) == ("127.0.0.1", 45123, False)
    db.refresh(node)
    assert node.ssh_host_key == "ssh-ed25519 AAAAC3NzaPersisted"


def test_to_response_derives_mtls_from_transport(db):
    from app.routers import nodes as nodes_router

    node = _add_node(db, transport="mtls")
    resp = nodes_router._to_response(node)
    assert resp.transport == "mtls"
    assert resp.mtls_enabled is True


def test_delete_node_drops_ssh_tunnel(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "find_group_for_node", lambda _db, _id: None)
    monkeypatch.setattr(nodes_router, "sync_local_node", lambda _db: None)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    pool = MagicMock()
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: pool)
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()

    resp = nodes_router.delete_node(node.id, request, admin=admin, db=db)

    assert "удалён" in resp.message
    pool.drop.assert_called_once_with(node.id)


def test_enable_mtls_endpoint_rejects_ssh_transport(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")

    with pytest.raises(HTTPException) as exc:
        nodes_router.enable_node_mtls(node.id, admin=admin, db=db)

    assert exc.value.status_code == 400
    assert "transport" in str(exc.value.detail).lower()
    assert "picker" in str(exc.value.detail).lower()


def test_disable_mtls_endpoint_rejects_ssh_transport(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")

    with pytest.raises(HTTPException) as exc:
        nodes_router.disable_node_mtls(node.id, admin=admin, db=db)

    assert exc.value.status_code == 400
    assert "transport" in str(exc.value.detail).lower()
    assert "picker" in str(exc.value.detail).lower()


def test_create_node_with_ssh_transport(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.schemas import NodeCreate

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "is_node_ssh_transport_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "validate_node_host", lambda host: host)
    monkeypatch.setattr(nodes_router, "store_api_key", lambda _h, key: ("hash", "enc"))
    monkeypatch.setattr(nodes_router, "check_node_health", lambda *a, **k: {"status": "online"})
    monkeypatch.setattr(nodes_router, "update_node_from_health", lambda *a, **k: None)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(nodes_router, "get_active_node_id", lambda _db: 1)
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: MagicMock())

    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    payload = NodeCreate(
        name="vpn-ssh-1",
        host="10.0.0.5",
        api_key="secret-key-1",
        transport="ssh",
        ssh_username="root",
        ssh_private_key="PRIVATE KEY MATERIAL",
        ssh_port=22,
    )
    resp = nodes_router.create_node(payload, request, admin=admin, db=db)
    assert resp.transport == "ssh"
    assert resp.ssh_host == "10.0.0.5"
    assert resp.ssh_username == "root"
    assert resp.ssh_key_configured is True
    stored = db.query(Node).filter(Node.id == resp.id).one()
    assert stored.transport == "ssh"
    assert stored.ssh_private_key_encrypted


def test_create_node_ssh_rejected_when_toggle_off(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.schemas import NodeCreate

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "is_node_ssh_transport_enabled", lambda _db: False)
    monkeypatch.setattr(nodes_router, "validate_node_host", lambda host: host)
    monkeypatch.setattr(nodes_router, "store_api_key", lambda _h, key: ("hash", "enc"))
    monkeypatch.setattr(nodes_router, "get_active_node_id", lambda _db: 1)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)

    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    payload = NodeCreate(
        name="vpn-ssh-2",
        host="10.0.0.6",
        api_key="secret-key-1",
        transport="ssh",
        ssh_username="root",
        ssh_private_key="PRIVATE KEY",
    )
    with pytest.raises(HTTPException) as exc:
        nodes_router.create_node(payload, request, admin=admin, db=db)
    assert exc.value.status_code == 403
    assert "SSH transport узлов" in str(exc.value.detail)
    assert db.query(Node).filter(Node.name == "vpn-ssh-2").count() == 0


def test_create_node_ssh_failure_removes_orphan(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.schemas import NodeCreate

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "is_node_ssh_transport_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "validate_node_host", lambda host: host)
    monkeypatch.setattr(nodes_router, "store_api_key", lambda _h, key: ("hash", "enc"))
    monkeypatch.setattr(nodes_router, "get_active_node_id", lambda _db: 1)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: MagicMock())

    def _boom(*_a, **_k):
        raise HTTPException(status_code=400, detail="ssh_host обязателен для SSH transport")

    monkeypatch.setattr(nodes_router, "_apply_ssh_transport_update", _boom)

    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    payload = NodeCreate(
        name="vpn-ssh-orphan",
        host="10.0.0.66",
        api_key="secret-key-1",
        transport="ssh",
        ssh_username="root",
        ssh_private_key="PRIVATE KEY",
    )
    with pytest.raises(HTTPException) as exc:
        nodes_router.create_node(payload, request, admin=admin, db=db)
    assert exc.value.status_code == 400
    assert db.query(Node).filter(Node.name == "vpn-ssh-orphan").count() == 0


def test_create_node_mtls_failure_removes_orphan(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.schemas import NodeCreate

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "validate_node_host", lambda host: host)
    monkeypatch.setattr(nodes_router, "store_api_key", lambda _h, key: ("hash", "enc"))
    monkeypatch.setattr(nodes_router, "get_active_node_id", lambda _db: 1)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: MagicMock())

    def _boom(*_a, **_k):
        raise HTTPException(status_code=503, detail="agent offline")

    monkeypatch.setattr(nodes_router, "enable_mtls", _boom)

    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    payload = NodeCreate(
        name="vpn-mtls-orphan",
        host="10.0.0.67",
        api_key="secret-key-1",
        transport="mtls",
    )
    with pytest.raises(HTTPException) as exc:
        nodes_router.create_node(payload, request, admin=admin, db=db)
    assert exc.value.status_code == 503
    assert db.query(Node).filter(Node.name == "vpn-mtls-orphan").count() == 0


def test_patch_transport_ssh_to_mtls_rejected(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")
    enable = MagicMock()
    monkeypatch.setattr(nodes_router, "enable_mtls", enable)

    with pytest.raises(HTTPException) as exc:
        nodes_router.patch_node_transport(
            node.id,
            NodeTransportUpdate(transport="mtls"),
            admin=admin,
            db=db,
        )
    assert exc.value.status_code == 400
    assert "HTTP" in str(exc.value.detail)
    enable.assert_not_called()
    db.refresh(node)
    assert node.transport == "ssh"


def test_patch_existing_ssh_to_http_real_disable(db, monkeypatch):
    """Existing SSH node → HTTP must not 500 and must drop the tunnel."""
    from app.routers import nodes as nodes_router
    from app.services import node_mtls_provision

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    _allow_preflight(monkeypatch, nodes_router, current="ssh", wanted="http")
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(node_mtls_provision, "get_settings", lambda: SimpleNamespace(audit_log_enabled=False))
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")
    pool = MagicMock()
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: pool)

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(transport="http"),
        admin=admin,
        db=db,
    )
    assert resp.transport == "http"
    assert resp.mtls_enabled is False
    db.refresh(node)
    assert node.transport == "http"
    assert node.mtls_enabled is False
    pool.drop.assert_called_once_with(node.id)


def test_patch_existing_mtls_to_http(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.services import node_mtls_provision

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    _allow_preflight(monkeypatch, nodes_router, current="mtls", wanted="http")
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(node_mtls_provision, "get_settings", lambda: SimpleNamespace(audit_log_enabled=False))
    node = _add_node(db, transport="mtls")
    admin = SimpleNamespace(id=1, username="admin")
    pool = MagicMock()
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: pool)

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(transport="http"),
        admin=admin,
        db=db,
    )
    assert resp.transport == "http"
    assert resp.mtls_enabled is False
    db.refresh(node)
    assert node.transport == "http"
    pool.drop.assert_not_called()


def test_patch_existing_mtls_to_ssh(db, monkeypatch):
    """mTLS → SSH is allowed (agent may already be demoted to HTTP); clears mtls flag."""
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    _allow_preflight(monkeypatch, nodes_router, current="mtls", wanted="ssh")
    monkeypatch.setattr(nodes_router, "is_node_ssh_transport_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "validate_node_host", lambda host: host)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: MagicMock())
    node = _add_node(db, transport="mtls")
    admin = SimpleNamespace(id=1, username="admin")

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(
            transport="ssh",
            ssh_host="203.0.113.10",
            ssh_username="root",
            ssh_private_key="PRIVATE KEY MATERIAL",
        ),
        admin=admin,
        db=db,
    )
    assert resp.transport == "ssh"
    assert resp.mtls_enabled is False
    db.refresh(node)
    assert node.transport == "ssh"
    assert node.mtls_enabled is False


def test_patch_existing_http_to_ssh(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    _allow_preflight(monkeypatch, nodes_router, current="http", wanted="ssh")
    monkeypatch.setattr(nodes_router, "is_node_ssh_transport_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "validate_node_host", lambda host: host)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(nodes_router, "get_ssh_tunnel_pool", lambda: MagicMock())
    node = _add_node(db, transport="http")
    admin = SimpleNamespace(id=1, username="admin")

    resp = nodes_router.patch_node_transport(
        node.id,
        NodeTransportUpdate(
            transport="ssh",
            ssh_host="203.0.113.11",
            ssh_username="deploy",
            ssh_private_key="PRIVATE KEY MATERIAL",
            ssh_port=2222,
        ),
        admin=admin,
        db=db,
    )
    assert resp.transport == "ssh"
    assert resp.ssh_username == "deploy"
    assert resp.ssh_port == 2222
    db.refresh(node)
    assert node.transport == "ssh"


def test_create_node_with_mtls_transport(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.schemas import NodeCreate

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(nodes_router, "validate_node_host", lambda host: host)
    monkeypatch.setattr(nodes_router, "store_api_key", lambda _h, key: ("hash", "enc"))
    monkeypatch.setattr(nodes_router, "check_node_health", lambda *a, **k: {"status": "online"})
    monkeypatch.setattr(nodes_router, "update_node_from_health", lambda *a, **k: None)
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)
    monkeypatch.setattr(nodes_router, "get_active_node_id", lambda _db: 1)

    def _enable(db_session, node, _admin):
        node.transport = "mtls"
        node.mtls_enabled = True
        db_session.add(node)
        db_session.commit()
        db_session.refresh(node)
        return node

    monkeypatch.setattr(nodes_router, "enable_mtls", _enable)

    admin = SimpleNamespace(id=1, username="admin")
    request = MagicMock()
    payload = NodeCreate(
        name="vpn-mtls-1",
        host="10.0.0.7",
        api_key="secret-key-1",
        transport="mtls",
    )
    resp = nodes_router.create_node(payload, request, admin=admin, db=db)
    assert resp.transport == "mtls"
    assert resp.mtls_enabled is True

def test_preflight_ssh_to_mtls_blocked(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")

    resp = nodes_router.preflight_node_transport(
        node.id,
        NodeTransportUpdate(transport="mtls"),
        admin,
        db=db,
    )
    assert resp.ok is False
    assert "mTLS" in resp.message or "SSH" in resp.message


def test_preflight_http_ok_when_probe_online(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.services import node_transport_preflight as pf

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(pf, "get_api_key_plain", lambda _n: "secret")
    monkeypatch.setattr(pf, "_probe_direct", lambda *a, **k: (True, "online", None))
    node = _add_node(db, transport="ssh")

    resp = nodes_router.preflight_node_transport(
        node.id,
        NodeTransportUpdate(transport="http"),
        SimpleNamespace(id=1, username="admin"),
        db=db,
    )
    assert resp.ok is True
    assert resp.probe_status == "online"


def test_preflight_http_blocks_when_probe_offline(db, monkeypatch):
    from app.routers import nodes as nodes_router
    from app.services import node_transport_preflight as pf

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    monkeypatch.setattr(pf, "get_api_key_plain", lambda _n: "secret")
    monkeypatch.setattr(pf, "_probe_direct", lambda *a, **k: (False, "offline", "connection refused"))
    node = _add_node(db, transport="ssh")

    resp = nodes_router.preflight_node_transport(
        node.id,
        NodeTransportUpdate(transport="http"),
        SimpleNamespace(id=1, username="admin"),
        db=db,
    )
    assert resp.ok is False
    assert resp.probe_error == "connection refused"


def test_patch_blocked_when_preflight_fails(db, monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: True)
    node = _add_node(db, transport="ssh")
    admin = SimpleNamespace(id=1, username="admin")
    monkeypatch.setattr(
        nodes_router,
        "preflight_transport_switch",
        lambda *_a, **_k: SimpleNamespace(
            ok=False,
            current="ssh",
            wanted="http",
            message="Агент не отвечает",
            hint="hint",
            probe_status="offline",
            probe_error="refused",
            http_status=400,
        ),
    )
    disable = MagicMock()
    monkeypatch.setattr(nodes_router, "disable_mtls", disable)

    with pytest.raises(HTTPException) as exc:
        nodes_router.patch_node_transport(
            node.id,
            NodeTransportUpdate(transport="http"),
            admin=admin,
            db=db,
        )
    assert exc.value.status_code == 400
    assert "Агент не отвечает" in str(exc.value.detail)
    disable.assert_not_called()
    db.refresh(node)
    assert node.transport == "ssh"

