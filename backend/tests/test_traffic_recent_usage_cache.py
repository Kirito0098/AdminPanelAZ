"""Traffic overview _recent_usage TTL cache."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from app.services.traffic import collector as coll

_SINCE_A = datetime(2024, 6, 1, 0, 0, 0)
_UNTIL_A = datetime(2024, 7, 1, 0, 0, 0)
_SINCE_B = datetime(2024, 5, 1, 0, 0, 0)
_UNTIL_B = datetime(2024, 6, 1, 0, 0, 0)
_UNTIL_A2 = datetime(2024, 7, 1, 0, 0, 15)


def test_recent_usage_cache_hits_within_ttl(monkeypatch):
    coll.clear_recent_usage_cache()
    queries = {"n": 0}

    class _Query:
        def filter(self, *_a, **_k):
            return self

        def group_by(self, *_a, **_k):
            return self

        def all(self):
            queries["n"] += 1
            return []

    db = MagicMock()
    db.query.return_value = _Query()
    svc = coll.TrafficCollectorService(db, 1)

    first = svc._recent_usage(
        [1], since_utc=_SINCE_A, until_utc=_UNTIL_A, ttl_seconds=60, cache_period="30d"
    )
    second = svc._recent_usage(
        [1], since_utc=_SINCE_A, until_utc=_UNTIL_A, ttl_seconds=60, cache_period="30d"
    )
    assert first == {}
    assert second == {}
    assert queries["n"] == 1

    coll.clear_recent_usage_cache()
    third = svc._recent_usage(
        [1], since_utc=_SINCE_A, until_utc=_UNTIL_A, ttl_seconds=60, cache_period="30d"
    )
    assert queries["n"] == 2
    assert third == {}


def test_recent_usage_cache_bypass_with_ttl_none(monkeypatch):
    coll.clear_recent_usage_cache()
    queries = {"n": 0}

    class _Query:
        def filter(self, *_a, **_k):
            return self

        def group_by(self, *_a, **_k):
            return self

        def all(self):
            queries["n"] += 1
            return []

    db = MagicMock()
    db.query.return_value = _Query()
    svc = coll.TrafficCollectorService(db, 1)

    svc._recent_usage([1], since_utc=_SINCE_A, until_utc=_UNTIL_A, ttl_seconds=None)
    svc._recent_usage([1], since_utc=_SINCE_A, until_utc=_UNTIL_A, ttl_seconds=None)
    assert queries["n"] == 2


def test_recent_usage_cache_key_separates_preset_periods():
    coll.clear_recent_usage_cache()
    queries = {"n": 0}

    class _Query:
        def filter(self, *_a, **_k):
            return self

        def group_by(self, *_a, **_k):
            return self

        def all(self):
            queries["n"] += 1
            return []

    db = MagicMock()
    db.query.return_value = _Query()
    svc = coll.TrafficCollectorService(db, 1)

    svc._recent_usage(
        [1], since_utc=_SINCE_A, until_utc=_UNTIL_A, ttl_seconds=60, cache_period="7d"
    )
    svc._recent_usage(
        [1], since_utc=_SINCE_B, until_utc=_UNTIL_B, ttl_seconds=60, cache_period="30d"
    )
    assert queries["n"] == 2


def test_recent_usage_preset_cache_survives_sliding_until():
    """Preset polls move until_utc every request — cache must still hit."""
    coll.clear_recent_usage_cache()
    queries = {"n": 0}

    class _Query:
        def filter(self, *_a, **_k):
            return self

        def group_by(self, *_a, **_k):
            return self

        def all(self):
            queries["n"] += 1
            return []

    db = MagicMock()
    db.query.return_value = _Query()
    svc = coll.TrafficCollectorService(db, 1)

    svc._recent_usage(
        [1], since_utc=_SINCE_A, until_utc=_UNTIL_A, ttl_seconds=60, cache_period="30d"
    )
    svc._recent_usage(
        [1], since_utc=_SINCE_A, until_utc=_UNTIL_A2, ttl_seconds=60, cache_period="30d"
    )
    assert queries["n"] == 1


def test_recent_usage_window_key_without_period_label():
    coll.clear_recent_usage_cache()
    queries = {"n": 0}

    class _Query:
        def filter(self, *_a, **_k):
            return self

        def group_by(self, *_a, **_k):
            return self

        def all(self):
            queries["n"] += 1
            return []

    db = MagicMock()
    db.query.return_value = _Query()
    svc = coll.TrafficCollectorService(db, 1)

    svc._recent_usage([1], since_utc=_SINCE_A, until_utc=_UNTIL_A, ttl_seconds=60)
    svc._recent_usage([1], since_utc=_SINCE_B, until_utc=_UNTIL_B, ttl_seconds=60)
    assert queries["n"] == 2
