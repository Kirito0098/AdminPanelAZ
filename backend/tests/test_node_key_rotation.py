"""Automatic node API key rotation: due condition, key age tracking, and loop resilience."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.services.node_key_rotation as rotation
from app import database
from app.database import Base
from app.models import Node
from app.services.node_manager import (
    get_api_key_plain,
    get_pending_api_key_plain,
    store_api_key,
    store_pending_api_key,
)

PENDING = "pending-key-0123456789abcdef0123456789"


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(rotation, "get_settings", lambda: SimpleNamespace(node_api_key_rotation_days=30, audit_log_enabled=False))
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _node(name: str, *, created_days_ago: int, rotated_days_ago: int | None = None, **kwargs) -> Node:
    now = datetime.utcnow()
    key_hash, key_encrypted = store_api_key("", f"key-{name}")
    return Node(
        name=name,
        host="10.0.0.2",
        api_key_hash=key_hash,
        api_key_encrypted=key_encrypted,
        is_local=kwargs.pop("is_local", False),
        created_at=now - timedelta(days=created_days_ago),
        api_key_rotated_at=None if rotated_days_ago is None else now - timedelta(days=rotated_days_ago),
        **kwargs,
    )


def test_due_nodes_follow_key_age_not_health_updates(db):
    db.add_all(
        [
            _node("old-key", created_days_ago=90, rotated_days_ago=40),
            _node("fresh-key", created_days_ago=90, rotated_days_ago=5),
            _node("never-rotated-old", created_days_ago=40),
            _node("never-rotated-new", created_days_ago=3),
            _node("local", created_days_ago=90, is_local=True),
            _node("proxy", created_days_ago=90, node_kind="proxy"),
        ]
    )
    db.commit()
    # Health checks touch every node row, which used to reset the rotation clock.
    for node in db.query(Node).all():
        node.last_seen_at = datetime.utcnow()
    db.commit()

    due = sorted(node.name for node in rotation._nodes_due_for_rotation(db))

    assert due == ["never-rotated-old", "old-key"]


def test_rotation_records_key_age(db):
    node = _node("vpn", created_days_ago=90, rotated_days_ago=40)
    db.add(node)
    db.commit()
    rotated: list[str] = []

    class _Adapter:
        def rotate_api_key(self, new_key):
            rotated.append(new_key)

    with patch.object(rotation, "get_adapter_for_node", lambda _node: _Adapter()):
        rotation.rotate_node_api_key(db, node, actor_username="system")

    assert rotated
    assert node.api_key_rotated_at is not None
    assert datetime.utcnow() - node.api_key_rotated_at < timedelta(minutes=1)
    assert rotation._nodes_due_for_rotation(db) == []


def test_proxy_node_rotation_is_rejected_before_calling_agent(db):
    node = _node("proxy", created_days_ago=90, node_kind="proxy")
    db.add(node)
    db.commit()

    with patch.object(rotation, "get_adapter_for_node", side_effect=AssertionError("agent must not be called")):
        with pytest.raises(ValueError):
            rotation.rotate_node_api_key(db, node)


def _record_rotation(monkeypatch) -> list[tuple[str, str, str]]:
    from app.services.node_adapter import RemoteNodeAdapter

    calls: list[tuple[str, str, str]] = []

    def fake_rotate(self, new_key):
        calls.append((self.base_url, self.api_key, new_key))

    monkeypatch.setattr(RemoteNodeAdapter, "rotate_api_key", fake_rotate)
    return calls


def test_rotation_of_ssh_node_goes_through_the_tunnel(db, monkeypatch):
    node = _node("vpn-ssh", created_days_ago=90, transport="ssh", port=9100)
    db.add(node)
    db.commit()
    calls = _record_rotation(monkeypatch)

    class _Pool:
        def ensure(self, _node):
            return 45123

    monkeypatch.setattr("app.services.ssh_tunnel_pool.get_ssh_tunnel_pool", lambda: _Pool())

    new_key = rotation.rotate_node_api_key(db, node)

    assert calls == [("http://127.0.0.1:45123", "key-vpn-ssh", new_key)]


def test_rotation_of_http_node_talks_to_the_node_directly(db, monkeypatch):
    node = _node("vpn-http", created_days_ago=90, port=9100)
    db.add(node)
    db.commit()
    calls = _record_rotation(monkeypatch)

    new_key = rotation.rotate_node_api_key(db, node)

    assert calls == [("http://10.0.0.2:9100", "key-vpn-http", new_key)]


def test_manual_key_change_resets_key_age(db, monkeypatch):
    from unittest.mock import MagicMock

    from app.routers import nodes as nodes_router
    from app.schemas import NodeUpdate

    node = _node("vpn", created_days_ago=90, rotated_days_ago=40)
    db.add(node)
    db.commit()
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)

    nodes_router.update_node(
        node.id,
        NodeUpdate(api_key="new-secret-key"),
        MagicMock(),
        admin=SimpleNamespace(id=1, username="admin"),
        db=db,
    )

    db.refresh(node)
    assert datetime.utcnow() - node.api_key_rotated_at < timedelta(minutes=1)
    assert rotation._nodes_due_for_rotation(db) == []


def _run_loop(monkeypatch, iterations: int, rotate_once) -> None:
    monkeypatch.setattr(
        rotation,
        "get_settings",
        lambda: SimpleNamespace(node_api_key_rotation_check_hours=0, node_api_key_rotation_days=30),
    )
    monkeypatch.setattr(rotation, "_is_key_rotation_enabled", lambda: True)
    monkeypatch.setattr(rotation, "_rotate_due_nodes_once", rotate_once)
    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > iterations:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(rotation.asyncio, "sleep", side_effect=fake_sleep):
            await rotation.run_node_key_rotation_loop()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())


def test_loop_survives_a_failing_iteration(monkeypatch):
    calls: list[int] = []

    def rotate_once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database is locked")

    _run_loop(monkeypatch, 2, rotate_once)

    assert len(calls) == 2


def test_loop_rotates_off_the_event_loop_thread(monkeypatch):
    main_thread = threading.get_ident()
    threads: list[int] = []

    _run_loop(monkeypatch, 1, lambda: threads.append(threading.get_ident()))

    assert threads and threads[0] != main_thread


def test_migration_adds_pending_api_key_column(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE nodes (id INTEGER PRIMARY KEY, name VARCHAR(128))"))
        conn.execute(text("INSERT INTO nodes (id, name) VALUES (1, 'old')"))
    monkeypatch.setattr(database, "engine", engine)

    database._migrate_nodes_api_key_pending()
    database._migrate_nodes_api_key_pending()

    with engine.connect() as conn:
        value = conn.execute(text("SELECT api_key_pending_encrypted FROM nodes WHERE id = 1")).scalar()
    assert value == ""
    engine.dispose()


def test_pending_key_is_stored_encrypted(db):
    node = _node("vpn", created_days_ago=1)
    assert get_pending_api_key_plain(node) is None

    store_pending_api_key(node, PENDING)

    assert node.api_key_pending_encrypted
    assert PENDING not in node.api_key_pending_encrypted
    assert get_pending_api_key_plain(node) == PENDING


class _RecordingAdapter:
    def __init__(self, error: Exception | None = None):
        self.sent: list[str] = []
        self.error = error

    def rotate_api_key(self, new_key):
        self.sent.append(new_key)
        if self.error:
            raise self.error


def _agent_accepting(*keys):
    def check(_node, api_key_override=None):
        if api_key_override in keys:
            return {"status": "online"}
        return {"status": "offline", "error_code": "node_auth"}

    return check


def test_rotation_commits_pending_key_before_calling_agent(db):
    node = _node("vpn", created_days_ago=90)
    db.add(node)
    db.commit()
    seen_pending: list[str | None] = []

    class _Adapter:
        def rotate_api_key(self, new_key):
            db.rollback()
            db.refresh(node)
            seen_pending.append(get_pending_api_key_plain(node))

    with patch.object(rotation, "get_adapter_for_node", lambda _node: _Adapter()):
        new_key = rotation.rotate_node_api_key(db, node)

    assert seen_pending == [new_key]
    assert get_api_key_plain(node) == new_key
    assert node.api_key_pending_encrypted == ""


def test_lost_agent_reply_still_completes_rotation(db, monkeypatch):
    node = _node("vpn", created_days_ago=90)
    db.add(node)
    db.commit()
    adapter = _RecordingAdapter(RuntimeError("read timeout"))
    monkeypatch.setattr(rotation, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(
        rotation,
        "check_node_health",
        lambda _node, api_key_override=None: {"status": "online" if api_key_override in adapter.sent else "offline"},
    )

    new_key = rotation.rotate_node_api_key(db, node)

    assert adapter.sent == [new_key]
    assert get_api_key_plain(node) == new_key
    assert node.api_key_pending_encrypted == ""


def test_failed_rotation_keeps_old_key_and_retry_reuses_pending(db, monkeypatch):
    node = _node("vpn", created_days_ago=90)
    db.add(node)
    db.commit()
    adapter = _RecordingAdapter(RuntimeError("connection refused"))
    monkeypatch.setattr(rotation, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(rotation, "check_node_health", lambda _node, api_key_override=None: {"status": "offline"})

    with pytest.raises(RuntimeError):
        rotation.rotate_node_api_key(db, node)

    db.refresh(node)
    assert get_api_key_plain(node) == "key-vpn"
    first_pending = get_pending_api_key_plain(node)
    assert first_pending

    adapter.error = None
    new_key = rotation.rotate_node_api_key(db, node)

    assert new_key == first_pending
    assert adapter.sent == [first_pending, first_pending]
    assert get_api_key_plain(node) == first_pending


def test_complete_promotes_pending_key_the_agent_already_uses(db, monkeypatch):
    node = _node("vpn", created_days_ago=90)
    store_pending_api_key(node, PENDING)
    db.add(node)
    db.commit()
    monkeypatch.setattr(rotation, "check_node_health", _agent_accepting(PENDING))

    with patch.object(rotation, "get_adapter_for_node", side_effect=AssertionError("agent must not be called")):
        assert rotation.complete_pending_key_rotation(db, node) is True

    assert get_api_key_plain(node) == PENDING
    assert node.api_key_pending_encrypted == ""


def test_complete_resends_pending_key_when_agent_still_on_old_key(db, monkeypatch):
    node = _node("vpn", created_days_ago=90)
    store_pending_api_key(node, PENDING)
    db.add(node)
    db.commit()
    adapter = _RecordingAdapter()
    monkeypatch.setattr(rotation, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(rotation, "check_node_health", _agent_accepting("key-vpn"))

    assert rotation.complete_pending_key_rotation(db, node) is True

    assert adapter.sent == [PENDING]
    assert get_api_key_plain(node) == PENDING
    assert node.api_key_pending_encrypted == ""


def test_complete_without_pending_key_does_nothing(db):
    node = _node("vpn", created_days_ago=90)
    db.add(node)
    db.commit()

    with patch.object(rotation, "check_node_health", side_effect=AssertionError("no probe expected")):
        assert rotation.complete_pending_key_rotation(db, node) is False


def test_manual_key_change_drops_pending_key(db, monkeypatch):
    from unittest.mock import MagicMock

    from app.routers import nodes as nodes_router
    from app.schemas import NodeUpdate

    node = _node("vpn", created_days_ago=90)
    store_pending_api_key(node, PENDING)
    db.add(node)
    db.commit()
    monkeypatch.setattr(nodes_router.settings, "audit_log_enabled", False)

    nodes_router.update_node(
        node.id,
        NodeUpdate(api_key="new-secret-key"),
        MagicMock(),
        admin=SimpleNamespace(id=1, username="admin"),
        db=db,
    )

    db.refresh(node)
    assert node.api_key_pending_encrypted == ""
    assert get_api_key_plain(node) == "new-secret-key"
