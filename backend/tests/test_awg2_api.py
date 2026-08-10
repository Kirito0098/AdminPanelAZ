"""AZ-AWG2 wave 1a: health/status router handlers (mocked adapter)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routers import awg2 as awg2_router
from app.services.awg2 import Awg2NotInstalledError, AWG2_INSTALL_CMD
from app.services.feature_guards import check_path_access
from app.services.feature_toggles import FeatureToggleService


def _svc(env_file: Path, **flags: bool) -> FeatureToggleService:
    lines = [f"{key}={'true' if value else 'false'}" for key, value in flags.items()]
    env_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return FeatureToggleService(env_file)


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
