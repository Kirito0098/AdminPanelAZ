"""Временный бан Buffer Guard и сверка политик OpenVPN с файлом banned_clients."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.node_manager as node_manager_mod
from app.database import Base
from app.models import Node, OpenVpnAccessPolicy, OpenVpnBufferGuardEvent, OpenVpnBufferGuardMode
from app.services import openvpn_buffer_guard as guard
from app.services.access_policy import AccessPolicyService


class NodeFilesAdapter:
    """Агент узла: banned_clients в памяти, без записи на диск."""

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.files: dict[str, str] = {}

    def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
        return {"ok": True, "unit": unit, "text": self.text, "error": None}

    def kill_openvpn_client(self, unit: str, client_name: str) -> dict:
        return {"success": True, "client_name": client_name}

    def restart_service(self, service_name: str) -> str:
        return "ok"

    def read_config_file(self, name: str) -> str:
        return self.files.get(name, "")

    def write_config_file(self, name: str, content: str) -> None:
        self.files[name] = content

    def ensure_openvpn_ban_check(self) -> dict:
        return {"success": True}

    def banned(self) -> set[str]:
        return {line for line in self.files.get("banned_clients", "").splitlines() if line.strip()}


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _node(db) -> Node:
    node = Node(name="node-a", host="10.0.0.2", is_local=False)
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _enobufs(common_name: str, count: int) -> str:
    return "\n".join([f"{common_name}/udp4:203.0.113.1:1194 note: No buffer space available"] * count)


def _policy_service(db, node: Node, adapter: NodeFilesAdapter) -> AccessPolicyService:
    return AccessPolicyService(db, antizapret_path=Path("/nonexistent-az"), node_id=node.id, adapter=adapter)


def _ban_event(db, node: Node, client: str, expires_at: datetime) -> OpenVpnBufferGuardEvent:
    ev = OpenVpnBufferGuardEvent(
        node_id=node.id,
        created_at=expires_at - timedelta(minutes=60),
        unit="antizapret-udp",
        common_name=client,
        error_count=200,
        window_seconds=60,
        mode=OpenVpnBufferGuardMode.kill_restart_temp_ban.value,
        actions_json="[]",
        result="banned",
        manual=False,
        ban_expires_at=expires_at,
    )
    db.add(ev)
    db.commit()
    return ev


def test_temp_ban_survives_traffic_limit_reconcile(db, monkeypatch):
    node = _node(db)
    db.add(OpenVpnAccessPolicy(node_id=node.id, client_name="noisy"))
    db.commit()
    guard.upsert_settings(
        db,
        node.id,
        {
            "enabled": True,
            "mode": OpenVpnBufferGuardMode.kill_restart_temp_ban.value,
            "threshold_count": 10,
            "escalate_after_seconds": 0,
            "temp_ban_minutes": 60,
            "watch_units": ["antizapret-udp"],
        },
    )
    monkeypatch.setattr(guard.admin_notify_service, "send", lambda *a, **k: None)
    adapter = NodeFilesAdapter(_enobufs("noisy", 20))

    results = guard.run_guard_pass(db, adapter, node.id)
    assert results[0]["result"] == "banned"
    assert "noisy" in adapter.banned()

    _policy_service(db, node, adapter).reconcile_all_traffic_limits(node_id=node.id)

    assert "noisy" in adapter.banned()


def test_temp_ban_survives_reconcile_without_policy_row(db):
    node = _node(db)
    adapter = NodeFilesAdapter()
    adapter.files["banned_clients"] = "noisy\n"
    _ban_event(db, node, "noisy", datetime.now(timezone.utc) + timedelta(minutes=30))

    _policy_service(db, node, adapter).reconcile_openvpn("noisy")

    assert "noisy" in adapter.banned()


def test_reconcile_ignores_bans_of_other_clients_and_nodes(db):
    node = _node(db)
    other_node = Node(name="node-b", host="10.0.0.3", is_local=False)
    db.add(other_node)
    db.add(OpenVpnAccessPolicy(node_id=node.id, client_name="calm"))
    db.commit()
    adapter = NodeFilesAdapter()
    adapter.files["banned_clients"] = "calm\n"
    later = datetime.now(timezone.utc) + timedelta(minutes=30)
    _ban_event(db, node, "noisy", later)
    _ban_event(db, other_node, "calm", later)

    _policy_service(db, node, adapter).reconcile_openvpn("calm")

    assert adapter.banned() == set()


def _expire_bans(db, monkeypatch, adapter: NodeFilesAdapter) -> list[dict]:
    monkeypatch.setattr(node_manager_mod, "get_adapter_for_node", lambda node: adapter)
    return guard.process_temp_ban_expiries(db)


def test_temp_ban_expiry_keeps_admin_block(db, monkeypatch):
    node = _node(db)
    adapter = NodeFilesAdapter()
    _policy_service(db, node, adapter).openvpn_permanent_block("noisy", actor="admin")
    assert "noisy" in adapter.banned()
    ev = _ban_event(db, node, "noisy", datetime.now(timezone.utc) - timedelta(seconds=1))

    results = _expire_bans(db, monkeypatch, adapter)

    assert "noisy" in adapter.banned()
    assert results == [{"node_id": node.id, "client_name": "noisy", "unbanned": False}]
    db.refresh(ev)
    assert ev.ban_expires_at is None


def test_temp_ban_expiry_lifts_guard_only_ban(db, monkeypatch):
    node = _node(db)
    db.add(OpenVpnAccessPolicy(node_id=node.id, client_name="noisy"))
    db.commit()
    adapter = NodeFilesAdapter()
    adapter.files["banned_clients"] = "noisy\nother\n"
    ev = _ban_event(db, node, "noisy", datetime.now(timezone.utc) - timedelta(seconds=1))

    results = _expire_bans(db, monkeypatch, adapter)

    assert adapter.banned() == {"other"}
    assert results == [{"node_id": node.id, "client_name": "noisy", "unbanned": True}]
    db.refresh(ev)
    assert ev.ban_expires_at is None


def test_expired_ban_does_not_lift_newer_active_ban(db, monkeypatch):
    node = _node(db)
    adapter = NodeFilesAdapter()
    adapter.files["banned_clients"] = "noisy\n"
    now = datetime.now(timezone.utc)
    old = _ban_event(db, node, "noisy", now - timedelta(seconds=1))
    _ban_event(db, node, "noisy", now + timedelta(minutes=30))

    _expire_bans(db, monkeypatch, adapter)

    assert "noisy" in adapter.banned()
    db.refresh(old)
    assert old.ban_expires_at is None
