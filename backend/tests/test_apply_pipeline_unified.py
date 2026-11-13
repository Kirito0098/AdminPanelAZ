"""One apply pipeline for routing apply, manual doall and CIDR deploy.

The three entry points used to repeat the steps with their own order and result
keys: routing apply (sync → doall ips → client.sh 7 → multihome), manual doall
(full doall → config queue) and CIDR deploy (sync → doall ips). They now share
``apply_routing_changes``; these tests pin the wiring, order and error semantics.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services import background_tasks as background_tasks_module
from app.services.cidr import apply_pipeline
from app.services.cidr.pipeline import orchestrator
from app.services.openvpn_profile_repair import RecreateResult

background_task_service = background_tasks_module.background_task_service


class _Calls:
    """Adapter stub: records the apply steps in call order."""

    def __init__(self) -> None:
        self.order: list[str] = []
        self.adapter = MagicMock()

    def _step(self, name: str, value):
        def _record(*_args, **_kwargs):
            self.order.append(name)
            return value

        return _record


@pytest.fixture
def adapter() -> MagicMock:
    return MagicMock()


@pytest.fixture
def spy_apply(monkeypatch):
    """Real helper plus captured kwargs, to pin what each caller asks for."""
    captured: list[dict] = []
    real = apply_pipeline.apply_routing_changes

    def _spy(adapter, **kwargs):
        captured.append(kwargs)
        return real(adapter, **kwargs)

    monkeypatch.setattr(background_tasks_module, "apply_routing_changes", _spy)
    return captured


@pytest.fixture
def profiles_ok(monkeypatch):
    def _recreate(adapter, hosts=None):
        adapter.recreate_profiles()
        return RecreateResult(success=True, recreated=True, output="profiles ok")

    monkeypatch.setattr(apply_pipeline, "recreate_openvpn_profiles", _recreate)


# --- step order per caller --------------------------------------------------


def test_routing_apply_order_sync_doall_profiles_multihome(monkeypatch, profiles_ok, spy_apply):
    calls = _Calls()
    adapter = calls.adapter
    adapter.sync_cidr_providers.side_effect = calls._step("sync", {"restored": []})
    adapter.apply_config_changes.side_effect = calls._step("doall", "doall ips ok")
    adapter.recreate_profiles.side_effect = calls._step("profiles", "profiles ok")
    adapter.ensure_openvpn_multihome.side_effect = calls._step("multihome", {"changed": True})

    result = background_task_service.task_routing_apply(adapter, ensure_openvpn_multihome=True)

    assert calls.order == ["sync", "doall", "profiles", "multihome"]
    adapter.apply_config_changes.assert_called_once_with(ips_only=True)
    assert spy_apply == [
        {
            "sync": True,
            "doall": True,
            "ips_only": True,
            "recreate_profiles": True,
            "hosts": None,
            "ensure_multihome": True,
            "progress": None,
        }
    ]
    assert result["message"] == "Маршрутизация применена (doall.sh)"
    stats = json.loads(result["output"].splitlines()[0])
    assert stats == {"restored": []}
    assert "doall ips ok" in result["output"]
    assert "profiles ok" in result["output"]


def test_run_doall_is_full_apply_plus_config_queue_without_profiles(
    profiles_ok, spy_apply, adapter
):
    adapter.apply_config_changes.return_value = "full doall ok"

    result = background_task_service.task_run_doall(adapter, recreate_profiles=False)

    adapter.apply_config_changes.assert_called_once_with(ips_only=False)
    adapter.sync_cidr_providers.assert_not_called()
    adapter.recreate_profiles.assert_not_called()
    assert spy_apply == [
        {
            "sync": False,
            "doall": True,
            "ips_only": False,
            "recreate_profiles": False,
            "hosts": None,
            "ensure_multihome": False,
            "run_config_queue": True,
            "progress": None,
        }
    ]
    assert result["message"] == "doall выполнен успешно (профили не пересоздавались)"
    assert result["output"] == "full doall ok"


def test_cidr_deploy_apply_syncs_and_runs_doall_ips_only(profiles_ok, adapter):
    adapter.sync_cidr_providers.return_value = {"restored": ["AP-1-include-ips.txt"]}
    adapter.apply_config_changes.return_value = "doall ips ok"

    result = orchestrator.run_apply(adapter, sync_after=True, apply_after=True)

    adapter.sync_cidr_providers.assert_called_once_with()
    adapter.apply_config_changes.assert_called_once_with(ips_only=True)
    adapter.recreate_profiles.assert_not_called()
    assert result["sync"] == {"restored": ["AP-1-include-ips.txt"]}
    assert result["doall_output"] == "doall ips ok"
    assert "profiles" not in result


def test_cidr_deploy_apply_without_doall_only_syncs(adapter):
    adapter.sync_cidr_providers.return_value = {"restored": []}

    result = orchestrator.run_apply(adapter, sync_after=True, apply_after=False)

    adapter.apply_config_changes.assert_not_called()
    assert list(result) == ["sync"]


def test_multihome_needs_doall(adapter):
    result = apply_pipeline.apply_routing_changes(
        adapter,
        sync=False,
        doall=False,
        recreate_profiles=False,
        ensure_multihome=True,
    )

    adapter.ensure_openvpn_multihome.assert_not_called()
    assert result == {}


# --- error semantics --------------------------------------------------------


def test_doall_error_skips_profiles_and_multihome(profiles_ok, adapter):
    adapter.apply_config_changes.side_effect = RuntimeError("doall.sh упал")

    with pytest.raises(RuntimeError, match="doall.sh упал"):
        background_task_service.task_routing_apply(adapter, ensure_openvpn_multihome=True)

    adapter.recreate_profiles.assert_not_called()
    adapter.ensure_openvpn_multihome.assert_not_called()


def test_profiles_error_keeps_applied_doall(monkeypatch, adapter):
    adapter.apply_config_changes.return_value = "doall ips ok"
    adapter.recreate_profiles.side_effect = RuntimeError("client.sh 7 упал")
    adapter.ensure_openvpn_multihome.return_value = {"changed": True}

    with pytest.raises(RuntimeError, match="recreate_profiles: client.sh 7 упал"):
        background_task_service.task_routing_apply(adapter, ensure_openvpn_multihome=True)

    # doall stays applied: it ran once, nothing was rolled back, multihome is not attempted.
    adapter.apply_config_changes.assert_called_once_with(ips_only=True)
    adapter.recreate_profiles.assert_called_once_with()
    adapter.ensure_openvpn_multihome.assert_not_called()


def test_sync_error_skips_doall(profiles_ok, adapter):
    adapter.sync_cidr_providers.side_effect = RuntimeError("узел недоступен")

    with pytest.raises(RuntimeError, match="узел недоступен"):
        background_task_service.task_routing_apply(adapter)

    adapter.apply_config_changes.assert_not_called()


# --- result keys ------------------------------------------------------------


def test_helper_reports_every_step_key(monkeypatch, profiles_ok, adapter):
    adapter.sync_cidr_providers.return_value = {"restored": []}
    adapter.apply_config_changes.return_value = "doall ok"
    adapter.ensure_openvpn_multihome.return_value = {"changed": False}

    result = apply_pipeline.apply_routing_changes(
        adapter,
        sync=True,
        doall=True,
        recreate_profiles=True,
        ensure_multihome=True,
        run_config_queue=True,
    )

    assert set(result) == {
        "sync",
        "doall_output",
        "profiles",
        "openvpn_multihome",
        "config_queue",
    }
    assert result["openvpn_multihome"] == {"changed": False}
    assert result["config_queue"] is True


def test_progress_texts_match_task_stages(profiles_ok, adapter):
    adapter.sync_cidr_providers.return_value = {"restored": []}
    adapter.apply_config_changes.return_value = "doall ok"
    adapter.ensure_openvpn_multihome.return_value = {"changed": True}
    stages: list[tuple[int, str]] = []

    background_task_service.task_routing_apply(
        adapter,
        lambda percent, stage, _message=None: stages.append((percent, stage)),
        ensure_openvpn_multihome=True,
    )

    assert stages == [
        (5, "Синхронизация провайдеров…"),
        (10, "AntiZapret: запуск doall.sh…"),
        (65, "AntiZapret: пересоздание профилей клиентов…"),
        (90, "AntiZapret: восстановление OpenVPN multihome…"),
    ]
