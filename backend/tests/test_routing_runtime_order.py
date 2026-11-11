"""Порядок применения настроек AntiZapret: fake-IP патчится до рестарта antizapret.

``antizapret.service`` запускает ``/root/antizapret/proxy.py``. Если перезапустить службу
раньше, чем панель перепишет ``--fake-cidr`` в proxy.py, новый fake-пул заработает только
при следующем рестарте, а up.sh уже поднимет правила под новые подсети.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException, status

from app.routers.routing import apply_antizapret_runtime_changes
from app.services.kresd_subnets import ClientSubnetsUnsupportedError
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter


class FakeAdapter:
    def __init__(self, subnets: str = "ok", settings: dict[str, str] | None = None) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.subnets = subnets
        self.settings = settings or {"alternative_client_ip": "y", "alternative_fake_ip": "y"}

    def get_antizapret_settings(self) -> dict[str, str]:
        self.calls.append(("settings",))
        return self.settings

    def apply_client_subnets(
        self, *, alternative_client_ip: bool, alternative_fake_ip: bool
    ) -> dict[str, Any]:
        self.calls.append(
            ("subnets", {"alternative_client_ip": alternative_client_ip, "alternative_fake_ip": alternative_fake_ip})
        )
        if self.subnets == "unsupported":
            raise NotImplementedError("подсети клиентов доступны только на VPN-узле")
        if self.subnets == "broken":
            raise RuntimeError("kresd@1 не запустился")
        return {"warnings": ["subnets"], "restarted": ["kresd@1"], "changed": True}

    def restart_service(self, service_name: str) -> str:
        self.calls.append(("restart", service_name))
        return ""

    def update_antizapret_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update", dict(updates)))
        return {"changes": 1}


def test_client_subnets_applied_before_antizapret_restart():
    adapter = FakeAdapter(settings={"alternative_client_ip": "y", "alternative_fake_ip": "n"})
    result: dict[str, Any] = {"changes": 1, "warnings": []}

    apply_antizapret_runtime_changes(adapter, {"alternative_fake_ip": "n"}, result)

    assert adapter.calls == [
        ("settings",),
        ("subnets", {"alternative_client_ip": True, "alternative_fake_ip": False}),
        ("restart", "antizapret"),
    ]
    assert result["warnings"] == ["subnets"]
    assert result["restarted"] == ["kresd@1"]
    assert result["antizapret_restarted"] is True


def test_unsupported_subnets_does_not_restart_antizapret():
    adapter = FakeAdapter(subnets="unsupported")
    result: dict[str, Any] = {"changes": 1, "warnings": []}

    apply_antizapret_runtime_changes(adapter, {"alternative_client_ip": "n"}, result)

    assert ("restart", "antizapret") not in adapter.calls
    assert any("обновите node agent" in warning for warning in result["warnings"])
    assert any("не перезапущена" in warning for warning in result["warnings"])


def test_other_runtime_keys_restart_without_subnets():
    adapter = FakeAdapter()
    result: dict[str, Any] = {"changes": 1, "warnings": []}

    apply_antizapret_runtime_changes(adapter, {"warp_endpoint": "1.2.3.4:500"}, result)

    assert adapter.calls == [("restart", "antizapret")]


def test_subnets_failure_does_not_restart_antizapret():
    adapter = FakeAdapter(subnets="broken")
    result: dict[str, Any] = {"changes": 1, "warnings": []}

    apply_antizapret_runtime_changes(adapter, {"alternative_fake_ip": "n"}, result)

    assert ("restart", "antizapret") not in adapter.calls
    assert any("не перезапущена" in warning for warning in result["warnings"])


def test_subnets_failure_rolls_back_setup():
    adapter = FakeAdapter(subnets="broken")
    result: dict[str, Any] = {"changes": 1, "needs_apply": True, "warnings": []}
    previous = {"alternative_client_ip": "y", "alternative_fake_ip": "y"}

    apply_antizapret_runtime_changes(
        adapter,
        {"alternative_fake_ip": "n"},
        result,
        previous_subnets=previous,
    )

    assert ("update", previous) in adapter.calls
    assert result["changes"] == 0
    assert result["needs_apply"] is False
    assert any("возвращены как были" in warning for warning in result["warnings"])


def test_retry_applies_subnets_even_without_setup_changes():
    adapter = FakeAdapter(settings={"alternative_client_ip": "y", "alternative_fake_ip": "n"})
    result: dict[str, Any] = {"changes": 0, "warnings": []}

    apply_antizapret_runtime_changes(adapter, {"alternative_fake_ip": "n"}, result)

    assert ("subnets", {"alternative_client_ip": True, "alternative_fake_ip": False}) in adapter.calls
    assert ("restart", "antizapret") in adapter.calls


def test_local_adapter_delegates_client_subnets():
    adapter = object.__new__(LocalNodeAdapter)
    adapter._service = FakeAdapter()

    adapter.apply_client_subnets(alternative_client_ip=True, alternative_fake_ip=False)

    assert adapter._service.calls == [
        ("subnets", {"alternative_client_ip": True, "alternative_fake_ip": False})
    ]


def test_remote_adapter_old_agent_answers_unsupported(monkeypatch):
    adapter = object.__new__(RemoteNodeAdapter)

    def _not_found(*_args: Any, **_kwargs: Any) -> dict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    monkeypatch.setattr(adapter, "_request", _not_found)

    with pytest.raises(ClientSubnetsUnsupportedError):
        adapter.apply_client_subnets(alternative_client_ip=True, alternative_fake_ip=True)
