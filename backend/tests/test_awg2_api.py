"""AZ-AWG2 wave 1a: health/status router handlers (mocked adapter)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models import UserRole, VpnType
from app.schemas import VpnConfigCreate
from app.routers import awg2 as awg2_router, configs as configs_router
from app.services.awg2 import Awg2NotInstalledError, AWG2_INSTALL_CMD
from app.services.feature_guards import check_path_access
from app.services.feature_toggles import FeatureToggleService


def _svc(env_file: Path, **flags: bool) -> FeatureToggleService:
    lines = [f"{key}={'true' if value else 'false'}" for key, value in flags.items()]
    env_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return FeatureToggleService(env_file)


class _QueryStub:
    def __init__(self, result):
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._result


class _FakeDb:
    def __init__(self, *, owner=None, existing=None):
        self.owner = owner
        self.existing = existing
        self.add = MagicMock()
        self.commit = MagicMock()
        self.refresh = MagicMock()
        self.delete = MagicMock()

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "User":
            return _QueryStub(self.owner)
        if name == "VpnConfig":
            return _QueryStub(self.existing)
        return _QueryStub(None)


def test_awg2_health_requires_toggle(tmp_path: Path):
    service = _svc(tmp_path / ".env", FEATURE_AWG2_ENABLED=False)
    blocked = check_path_access("/api/awg2/health", service=service)
    assert blocked is not None and blocked[0] == "awg2"


def test_awg2_health_ok():
    node = SimpleNamespace(id=1, name="local", host="127.0.0.1")
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {
        "installed": False,
        "missing_components": ["awg_client"],
        "install_command": AWG2_INSTALL_CMD,
        "update_command": AWG2_INSTALL_CMD + " --update",
    }
    db = MagicMock()
    with (
        patch.object(awg2_router, "get_active_node", return_value=node),
        patch.object(awg2_router, "get_active_adapter", return_value=adapter),
    ):
        result = awg2_router.awg2_health(db=db, _=SimpleNamespace())
    assert result["installed"] is False
    assert "blindtechnique/az-awg2" in result["install_command"]
    assert result["node_id"] == 1
    assert result["node_name"] == "local"


def test_awg2_health_installed_mock():
    node = SimpleNamespace(id=2, name="vpn-a", host="10.0.0.1")
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {
        "installed": True,
        "awg_client": True,
        "overlay_dir": True,
        "amnezia_dir": True,
        "missing_components": [],
        "install_command": AWG2_INSTALL_CMD,
        "update_command": AWG2_INSTALL_CMD + " --update",
    }
    with (
        patch.object(awg2_router, "get_active_node", return_value=node),
        patch.object(awg2_router, "get_active_adapter", return_value=adapter),
    ):
        result = awg2_router.awg2_health(db=MagicMock(), _=SimpleNamespace())
    assert result["installed"] is True
    assert result["missing_components"] == []


def test_awg2_status_maps_not_installed_to_409():
    node = SimpleNamespace(id=1, name="local", host="127.0.0.1")
    adapter = MagicMock()
    adapter.get_awg2_status.side_effect = Awg2NotInstalledError("not installed")
    with (
        patch.object(awg2_router, "get_active_node", return_value=node),
        patch.object(awg2_router, "get_active_adapter", return_value=adapter),
    ):
        with pytest.raises(HTTPException) as exc:
            awg2_router.awg2_status(db=MagicMock(), _=SimpleNamespace())
    assert exc.value.status_code == 409


def test_create_amneziawg2_calls_replicate_and_awg2():
    db = _FakeDb(owner=SimpleNamespace(id=1, username="owner"))
    current_user = SimpleNamespace(id=1, username="admin", role=UserRole.admin)
    payload = VpnConfigCreate(client_name="awg2user", vpn_type=VpnType.amneziawg2)
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {"installed": True}
    adapter.awg2_add_client.return_value = "ok"
    group = SimpleNamespace(id=7)

    with (
        patch.object(configs_router, "enforce_user_can_create_config"),
        patch.object(configs_router, "require_ha_primary_for_client_ops"),
        patch.object(configs_router, "require_vpn_type"),
        patch.object(configs_router, "enforce_can_create_vpn_type"),
        patch.object(configs_router, "_active_node_id", return_value=1),
        patch.object(configs_router, "get_active_adapter", return_value=adapter),
        patch.object(configs_router, "find_sync_group_for_primary", return_value=group),
        patch.object(configs_router, "maybe_replicate_create") as replicate,
        patch.object(configs_router, "refresh_config_cert_expiry"),
        patch.object(configs_router, "purge_traffic_history_for_reused_name"),
        patch.object(configs_router, "get_active_node", return_value=SimpleNamespace(id=1, name="node-1")),
        patch.object(configs_router.admin_notify_service, "send_config_create"),
        patch.object(configs_router, "get_client_timezone_from_request", return_value="UTC"),
        patch.object(configs_router, "_viewer_visibility_policy", return_value={}),
        patch.object(configs_router, "resolve_openvpn_group_for_user", return_value=None),
        patch.object(configs_router, "_local_ip_for_config", return_value=None),
        patch.object(configs_router, "_to_response", return_value={"ok": True}),
        patch.object(configs_router, "get_feature_service", return_value=SimpleNamespace()),
    ):
        result = configs_router.create_config(payload, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")), db, current_user)

    assert result == {"ok": True}
    adapter.awg2_add_client.assert_called_once_with("awg2user")
    adapter.add_wireguard_client.assert_not_called()
    replicate.assert_called_once()


def test_create_amneziawg2_not_installed_409():
    db = _FakeDb(owner=SimpleNamespace(id=1, username="owner"))
    current_user = SimpleNamespace(id=1, username="admin", role=UserRole.admin)
    payload = VpnConfigCreate(client_name="x", vpn_type=VpnType.amneziawg2)
    adapter = MagicMock()
    adapter.get_awg2_health.return_value = {
        "installed": False,
        "install_command": AWG2_INSTALL_CMD,
    }

    with (
        patch.object(configs_router, "enforce_user_can_create_config"),
        patch.object(configs_router, "require_ha_primary_for_client_ops"),
        patch.object(configs_router, "require_vpn_type"),
        patch.object(configs_router, "enforce_can_create_vpn_type"),
        patch.object(configs_router, "_active_node_id", return_value=1),
        patch.object(configs_router, "get_active_adapter", return_value=adapter),
        patch.object(configs_router, "get_feature_service", return_value=SimpleNamespace()),
        patch.object(configs_router, "get_client_timezone_from_request", return_value="UTC"),
    ):
        with pytest.raises(HTTPException) as exc:
            configs_router.create_config(payload, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")), db, current_user)

    assert exc.value.status_code == 409
    assert exc.value.detail["message"] == "AZ-AWG2 не установлен на узле"
    assert exc.value.detail["install_command"] == AWG2_INSTALL_CMD


def test_create_amneziawg2_health_probe_failure_409():
    db = _FakeDb(owner=SimpleNamespace(id=1, username="owner"))
    current_user = SimpleNamespace(id=1, username="admin", role=UserRole.admin)
    payload = VpnConfigCreate(client_name="x", vpn_type=VpnType.amneziawg2)
    adapter = MagicMock()
    adapter.get_awg2_health.side_effect = HTTPException(status_code=404, detail="missing")

    with (
        patch.object(configs_router, "enforce_user_can_create_config"),
        patch.object(configs_router, "require_ha_primary_for_client_ops"),
        patch.object(configs_router, "require_vpn_type"),
        patch.object(configs_router, "enforce_can_create_vpn_type"),
        patch.object(configs_router, "_active_node_id", return_value=1),
        patch.object(configs_router, "get_active_adapter", return_value=adapter),
        patch.object(configs_router, "get_feature_service", return_value=SimpleNamespace()),
        patch.object(configs_router, "get_client_timezone_from_request", return_value="UTC"),
    ):
        with pytest.raises(HTTPException) as exc:
            configs_router.create_config(payload, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")), db, current_user)

    assert exc.value.status_code == 409
    assert exc.value.detail["message"] == "AZ-AWG2 не установлен на узле"
    assert exc.value.detail["install_command"] == AWG2_INSTALL_CMD


def test_delete_amneziawg2_calls_replicate_and_awg2():
    db = _FakeDb()
    current_user = SimpleNamespace(id=1, username="admin", role=UserRole.admin)
    config = SimpleNamespace(id=11, client_name="awg2user", vpn_type=VpnType.amneziawg2)
    adapter = MagicMock()

    with (
        patch.object(configs_router, "_get_config_for_active_node", return_value=config),
        patch.object(configs_router, "_can_mutate_config", return_value=True),
        patch.object(configs_router, "require_ha_primary_for_client_ops"),
        patch.object(configs_router, "get_active_adapter", return_value=adapter),
        patch.object(configs_router, "get_active_node", return_value=SimpleNamespace(id=1, name="node-1")),
        patch.object(configs_router, "find_sync_group_for_primary", return_value=SimpleNamespace(id=7)),
        patch.object(configs_router, "maybe_replicate_delete") as replicate,
        patch.object(configs_router, "purge_ha_shadow_configs"),
        patch.object(configs_router.admin_notify_service, "send_config_delete"),
        patch.object(configs_router, "get_client_timezone_from_request", return_value="UTC"),
    ):
        result = configs_router.delete_config(11, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")), db, current_user)

    assert result.message == "Клиент 'awg2user' удалён"
    adapter.awg2_delete_client.assert_called_once_with("awg2user")
    adapter.delete_wireguard_client.assert_not_called()
    replicate.assert_called_once()
