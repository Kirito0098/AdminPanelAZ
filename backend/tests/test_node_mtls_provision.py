"""Enabling mTLS records the transport the agent actually answers on."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.node_mtls_provision as provision
from app.database import Base
from app.models import Node, NodeStatus

ONLINE = {"status": "online"}
OFFLINE = {"status": "offline", "error": "Таймаут ожидания node agent по HTTPS"}
ADMIN = SimpleNamespace(id=1, username="admin")


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


@pytest.fixture()
def node(db):
    node = Node(
        name="vpn",
        host="203.0.113.20",
        port=9100,
        api_key_hash="h",
        api_key_encrypted="enc",
        is_local=False,
        transport="http",
        mtls_enabled=False,
        node_kind="vpn",
        status=NodeStatus.online,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@pytest.fixture()
def http_agent(monkeypatch):
    """Agent that took the certificates but never answered over HTTPS within the wait."""
    adapter = MagicMock()
    adapter.provision_mtls.return_value = {"success": True}
    monkeypatch.setattr(provision, "RemoteNodeAdapter", MagicMock(return_value=adapter))
    monkeypatch.setattr(provision, "get_api_key_plain", lambda _node: "agent-key")
    monkeypatch.setattr(provision, "ensure_panel_mtls_materials", lambda: None)
    monkeypatch.setattr(provision, "generate_agent_cert_for_node", lambda *_args: None)
    monkeypatch.setattr(provision, "read_agent_bundle_for_node", lambda _node_id: MagicMock())
    monkeypatch.setattr(provision, "get_settings", lambda: SimpleNamespace(audit_log_enabled=False))
    monkeypatch.setattr(provision, "_wait_for_mtls_health", lambda _node: OFFLINE)
    return adapter


def test_agent_still_on_http_is_recorded_as_http(db, node, http_agent, monkeypatch):
    http_agent.health_check.return_value = {"agent_version": "1.11.1"}
    monkeypatch.setattr(provision, "check_node_health", MagicMock(side_effect=[ONLINE]))

    with pytest.raises(HTTPException) as exc:
        provision.enable_mtls(db, node, ADMIN)

    assert exc.value.status_code == 503
    assert "остался на HTTP" in exc.value.detail
    db.refresh(node)
    assert node.transport == "http"
    assert node.mtls_enabled is False


def test_agent_answering_https_late_keeps_mtls(db, node, http_agent, monkeypatch):
    http_agent.health_check.side_effect = RuntimeError("TLS handshake expected")
    monkeypatch.setattr(provision, "check_node_health", MagicMock(side_effect=[ONLINE, ONLINE]))
    updates: list[dict] = []
    monkeypatch.setattr(provision, "update_node_from_health", lambda _node, health, _db: updates.append(health))

    result = provision.enable_mtls(db, node, ADMIN)

    assert result.transport == "mtls"
    assert result.mtls_enabled is True
    assert updates == [ONLINE]


def test_silent_agent_keeps_mtls_and_is_reported_offline(db, node, http_agent, monkeypatch):
    http_agent.health_check.side_effect = RuntimeError("connection refused")
    monkeypatch.setattr(provision, "check_node_health", MagicMock(side_effect=[ONLINE, OFFLINE]))
    updates: list[dict] = []
    monkeypatch.setattr(provision, "update_node_from_health", lambda _node, health, _db: updates.append(health))

    with pytest.raises(HTTPException) as exc:
        provision.enable_mtls(db, node, ADMIN)

    assert exc.value.status_code == 503
    assert "ни по HTTPS, ни по HTTP" in exc.value.detail
    db.refresh(node)
    assert node.transport == "mtls"
    assert node.mtls_enabled is True
    assert updates == [OFFLINE]
