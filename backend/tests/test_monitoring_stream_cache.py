"""Monitoring SSE coalesce TTL and overview cache helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.routers import monitoring as mon


def test_stream_coalesce_ttl_below_interval(monkeypatch):
    monkeypatch.setattr(
        mon,
        "get_settings",
        lambda: MagicMock(monitoring_overview_cache_ttl_seconds=45),
    )
    assert mon._stream_coalesce_ttl(10) == 9
    assert mon._stream_coalesce_ttl(5) == 4


def test_stream_coalesce_ttl_respects_zero_cache(monkeypatch):
    monkeypatch.setattr(
        mon,
        "get_settings",
        lambda: MagicMock(monitoring_overview_cache_ttl_seconds=0),
    )
    assert mon._stream_coalesce_ttl(10) == 0


def test_stream_coalesce_ttl_caps_at_cache(monkeypatch):
    monkeypatch.setattr(
        mon,
        "get_settings",
        lambda: MagicMock(monitoring_overview_cache_ttl_seconds=3),
    )
    assert mon._stream_coalesce_ttl(10) == 3


def test_build_overview_uses_coalesce_ttl_not_bypass(monkeypatch):
    calls: list[tuple[str, int]] = []

    def fake_cached(key, ttl, fetcher):
        calls.append((key, ttl))
        overview = MagicMock()
        overview.model_copy = lambda update: overview
        return overview, False

    monkeypatch.setattr(mon, "get_cached_monitoring_overview", fake_cached)
    monkeypatch.setattr(mon, "build_federated_monitoring_overview", lambda db, ha_mode="dedupe": MagicMock())
    monkeypatch.setattr(mon, "_mark_cache_hit", lambda overview, _hit: overview)

    db = MagicMock()
    mon._build_monitoring_overview(
        db,
        scope="all",
        ha_mode="dedupe",
        cache_ttl=9,
        cache_key_prefix="sse:",
    )
    assert calls == [(f"sse:{mon.FEDERATED_OVERVIEW_CACHE_KEY}", 9)]


def test_sse_cache_key_isolated_from_rest(monkeypatch):
    keys: list[str] = []

    def fake_cached(key, ttl, fetcher):
        keys.append(key)
        return MagicMock(), False

    monkeypatch.setattr(mon, "get_cached_monitoring_overview", fake_cached)
    monkeypatch.setattr(mon, "build_federated_monitoring_overview", lambda db, ha_mode="dedupe": MagicMock())
    monkeypatch.setattr(mon, "_mark_cache_hit", lambda overview, _hit: overview)
    monkeypatch.setattr(
        mon,
        "get_settings",
        lambda: MagicMock(monitoring_overview_cache_ttl_seconds=45),
    )

    db = MagicMock()
    mon._build_monitoring_overview(db, scope="all")
    mon._build_monitoring_overview(db, scope="all", cache_ttl=9, cache_key_prefix="sse:")
    assert keys[0] == mon.FEDERATED_OVERVIEW_CACHE_KEY
    assert keys[1] == f"sse:{mon.FEDERATED_OVERVIEW_CACHE_KEY}"
    assert keys[0] != keys[1]


def test_build_node_overview_is_cached(monkeypatch):
    calls: list[tuple[str, int]] = []
    node = MagicMock(id=7)

    def fake_cached(key, ttl, fetcher):
        calls.append((key, ttl))
        overview = MagicMock()
        return overview, True

    monkeypatch.setattr(mon, "get_cached_monitoring_overview", fake_cached)
    monkeypatch.setattr(mon, "get_active_node", lambda db: node)
    monkeypatch.setattr(mon, "build_monitoring_overview_for_node", lambda db, n: MagicMock())
    monkeypatch.setattr(mon, "_mark_cache_hit", lambda overview, hit: overview)
    monkeypatch.setattr(
        mon,
        "get_settings",
        lambda: MagicMock(monitoring_overview_cache_ttl_seconds=45),
    )

    mon._build_monitoring_overview(MagicMock(), scope="node")
    assert calls == [("node:overview:7", 45)]
