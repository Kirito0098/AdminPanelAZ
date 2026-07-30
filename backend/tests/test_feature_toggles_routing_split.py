"""Routing vs AntiZapret config feature modules must be independent."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.feature_guards import PATH_TO_MODULES, check_path_access
from app.services.feature_toggles import FEATURE_TOGGLE_BY_KEY, FRONTEND_PATH_TO_MODULE, FeatureToggleService


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    return path


def _svc(env_file: Path, **flags: bool) -> FeatureToggleService:
    lines = [f"{key}={'true' if value else 'false'}" for key, value in flags.items()]
    env_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return FeatureToggleService(env_file)


def test_registry_splits_frontend_paths():
    assert FEATURE_TOGGLE_BY_KEY["routing"].frontend_paths == ("/routing",)
    assert FEATURE_TOGGLE_BY_KEY["antizapret_config"].frontend_paths == ("/antizapret",)
    assert FRONTEND_PATH_TO_MODULE["/routing"] == "routing"
    assert FRONTEND_PATH_TO_MODULE["/antizapret"] == "antizapret_config"


def test_antizapret_settings_api_bound_only_to_antizapret_config():
    assert PATH_TO_MODULES["/api/routing/antizapret-settings"] == ("antizapret_config",)
    assert "routing" in PATH_TO_MODULES["/api/routing/apply"]
    assert "antizapret_config" in PATH_TO_MODULES["/api/routing/apply"]


def test_disabling_routing_keeps_antizapret_config(env_file: Path):
    svc = _svc(env_file, FEATURE_ROUTING_ENABLED=False)
    assert svc.is_enabled("routing") is False
    assert svc.is_enabled("antizapret_config") is True
    assert check_path_access("/api/routing/antizapret-settings", service=svc) is None
    assert check_path_access("/api/routing/apply", service=svc) is None
    blocked = check_path_access("/api/routing/overview", service=svc)
    assert blocked is not None
    assert blocked[0] == "routing"
    assert check_path_access("/api/routing/cidr-db/status", service=svc) is not None


def test_disabling_antizapret_config_keeps_routing(env_file: Path):
    svc = _svc(
        env_file,
        FEATURE_ROUTING_ENABLED=True,
        FEATURE_ANTIZAPRET_CONFIG_ENABLED=False,
    )
    assert svc.is_enabled("routing") is True
    assert svc.is_enabled("antizapret_config") is False
    assert check_path_access("/api/routing/overview", service=svc) is None
    assert check_path_access("/api/routing/cidr-db/status", service=svc) is None
    blocked = check_path_access("/api/routing/antizapret-settings", service=svc)
    assert blocked is not None
    assert blocked[0] == "antizapret_config"
    # apply remains available via routing
    assert check_path_access("/api/routing/apply", service=svc) is None


def test_both_disabled_blocks_shared_and_specific_paths(env_file: Path):
    svc = _svc(
        env_file,
        FEATURE_ROUTING_ENABLED=False,
        FEATURE_ANTIZAPRET_CONFIG_ENABLED=False,
    )
    assert check_path_access("/api/routing/overview", service=svc) is not None
    assert check_path_access("/api/routing/antizapret-settings", service=svc) is not None
    assert check_path_access("/api/routing/apply", service=svc) is not None
