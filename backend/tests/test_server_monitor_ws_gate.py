"""WebSocket server_monitor runtime feature gate."""

from __future__ import annotations

from app.routers import server_monitor as router_mod


def test_is_server_monitor_enabled_delegates(monkeypatch):
    class Svc:
        def __init__(self, enabled: bool):
            self.enabled = enabled

        def is_enabled(self, key: str) -> bool:
            assert key == "server_monitor"
            return self.enabled

    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: Svc(False),
    )
    assert router_mod._is_server_monitor_enabled() is False

    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: Svc(True),
    )
    assert router_mod._is_server_monitor_enabled() is True
