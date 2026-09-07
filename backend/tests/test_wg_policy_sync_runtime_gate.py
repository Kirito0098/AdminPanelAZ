"""WG policy sync worker runtime gate for the wg_policy_sync toggle."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import app.services.wg_policy_sync_worker as worker


class SimpleEnabled:
    def __init__(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self, key: str) -> bool:
        assert key == "wg_policy_sync"
        return self._enabled


def test_wg_policy_loop_skips_when_toggle_disabled(monkeypatch):
    monkeypatch.setattr(worker, "_is_wg_policy_sync_enabled", lambda: False)
    monkeypatch.setattr(worker, "_startup_full_sync_done", True)
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("reconcile must not run while wg_policy_sync is disabled")

    monkeypatch.setattr(worker, "_reconcile_all_nodes_once", boom)

    class _Settings:
        wg_policy_sync_interval_seconds = 0

    monkeypatch.setattr(worker, "get_settings", lambda: _Settings())

    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch.object(worker.asyncio, "sleep", side_effect=fake_sleep):
            await worker.run_wg_policy_sync_loop()

    try:
        asyncio.run(run())
    except asyncio.CancelledError:
        pass

    assert called["n"] == 0
    assert sleeps >= 2


def test_is_wg_policy_sync_enabled_delegates(monkeypatch):
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(False),
    )
    assert worker._is_wg_policy_sync_enabled() is False
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: SimpleEnabled(True),
    )
    assert worker._is_wg_policy_sync_enabled() is True


def test_reconcile_skips_nodes_without_wg_policies(monkeypatch):
    db = MagicMock()
    node = MagicMock()
    node.id = 7

    monkeypatch.setattr(worker, "_is_vpn_node", lambda _n: True)

    node_q = MagicMock()
    node_q.all.return_value = [node]
    empty_policy_q = MagicMock()
    empty_policy_q.filter.return_value.limit.return_value.first.return_value = None

    def query_side_effect(arg):
        if arg is worker.Node:
            return node_q
        return empty_policy_q

    db.query.side_effect = query_side_effect

    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("must not reconcile empty-policy nodes")

    monkeypatch.setattr(worker, "_reconcile_for_node", boom)

    result = worker.reconcile_wg_policies_for_all_nodes(db, sync_all_runtime=False)
    assert result["nodes_processed"] == 0
    assert result["nodes_skipped_empty"] == 1
    assert called["n"] == 0


def test_should_start_wg_policy_sync_always_true():
    from app.services import worker_lifecycle as lifecycle

    assert lifecycle.should_start_wg_policy_sync() is True
