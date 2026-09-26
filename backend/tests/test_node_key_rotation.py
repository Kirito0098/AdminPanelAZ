"""Automatic node API key rotation: due condition, key age tracking, and loop resilience."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.node_key_rotation as rotation
from app.database import Base
from app.models import Node
from app.services.node_manager import store_api_key


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
        def __init__(self, **_kwargs):
            pass

        def rotate_api_key(self, new_key):
            rotated.append(new_key)

    with patch.object(rotation, "RemoteNodeAdapter", _Adapter):
        rotation.rotate_node_api_key(db, node, actor_username="system")

    assert rotated
    assert node.api_key_rotated_at is not None
    assert datetime.utcnow() - node.api_key_rotated_at < timedelta(minutes=1)
    assert rotation._nodes_due_for_rotation(db) == []


def test_proxy_node_rotation_is_rejected_before_calling_agent(db):
    node = _node("proxy", created_days_ago=90, node_kind="proxy")
    db.add(node)
    db.commit()

    with patch.object(rotation, "RemoteNodeAdapter", side_effect=AssertionError("agent must not be called")):
        with pytest.raises(ValueError):
            rotation.rotate_node_api_key(db, node)


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
