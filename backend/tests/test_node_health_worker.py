"""Health poll finishes an interrupted API key rotation once the agent answers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import app.services.node_health_worker as worker

AUTH_FAILED = {"status": "offline", "error_code": "node_auth"}
ONLINE = {"status": "online"}
TIMEOUT = {"status": "offline", "error": "timeout"}


def _poll(monkeypatch, node, healths, complete):
    db = MagicMock()
    db.query.return_value.all.return_value = [node]
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)
    answers = iter(healths)
    monkeypatch.setattr(worker, "check_node_health", lambda _node: next(answers))
    monkeypatch.setattr(worker, "complete_pending_key_rotation", complete)
    updates: list[dict] = []
    monkeypatch.setattr(worker, "update_node_from_health", lambda _node, health, _db: updates.append(health))
    worker._poll_all_nodes()
    return db, updates


def test_auth_failure_with_pending_key_finishes_rotation(monkeypatch):
    node = SimpleNamespace(name="vpn", api_key_pending_encrypted="enc")
    complete = MagicMock(return_value=True)

    _db, updates = _poll(monkeypatch, node, [AUTH_FAILED, ONLINE], complete)

    complete.assert_called_once()
    assert updates == [ONLINE]


def test_online_node_with_pending_key_finishes_rotation(monkeypatch):
    node = SimpleNamespace(name="vpn", api_key_pending_encrypted="enc")
    complete = MagicMock(return_value=True)

    _db, updates = _poll(monkeypatch, node, [ONLINE, ONLINE], complete)

    complete.assert_called_once()
    assert updates == [ONLINE]


def test_unreachable_node_keeps_pending_key_for_later(monkeypatch):
    node = SimpleNamespace(name="vpn", api_key_pending_encrypted="enc")
    complete = MagicMock()

    _db, updates = _poll(monkeypatch, node, [TIMEOUT], complete)

    complete.assert_not_called()
    assert updates == [TIMEOUT]


def test_node_without_pending_key_is_polled_as_before(monkeypatch):
    node = SimpleNamespace(name="vpn", api_key_pending_encrypted="")
    complete = MagicMock()

    _db, updates = _poll(monkeypatch, node, [AUTH_FAILED], complete)

    complete.assert_not_called()
    assert updates == [AUTH_FAILED]


def test_failed_completion_rolls_back_and_keeps_polling(monkeypatch):
    node = SimpleNamespace(name="vpn", api_key_pending_encrypted="enc")
    complete = MagicMock(side_effect=RuntimeError("agent refused"))

    db, updates = _poll(monkeypatch, node, [AUTH_FAILED], complete)

    db.rollback.assert_called_once()
    assert updates == [AUTH_FAILED]
