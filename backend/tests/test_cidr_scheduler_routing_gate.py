"""CIDR scheduler runtime gate for the routing feature toggle."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.cidr import cidr_scheduler as sched


def test_scheduler_may_run_requires_enabled_and_routing(monkeypatch):
    monkeypatch.setattr(sched, "_is_routing_module_enabled", lambda: True)
    assert sched._scheduler_may_run(SimpleNamespace(cidr_db_refresh_enabled=True)) is True
    assert sched._scheduler_may_run(SimpleNamespace(cidr_db_refresh_enabled=False)) is False

    monkeypatch.setattr(sched, "_is_routing_module_enabled", lambda: False)
    assert sched._scheduler_may_run(SimpleNamespace(cidr_db_refresh_enabled=True)) is False


def test_should_start_cidr_scheduler_always_true(monkeypatch):
    from app.services import worker_lifecycle as lifecycle

    class _Off:
        cidr_db_refresh_enabled = False

    monkeypatch.setattr(lifecycle, "get_settings", lambda: _Off())
    monkeypatch.setattr(
        lifecycle,
        "get_feature_service",
        lambda: SimpleNamespace(is_enabled=lambda _key: False),
    )
    assert lifecycle.should_start_cidr_scheduler() is True
