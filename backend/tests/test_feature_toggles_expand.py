from __future__ import annotations

from pathlib import Path

import pytest

from app.services.feature_toggles import (
    FEATURE_TOGGLE_BY_ENV,
    FEATURE_TOGGLE_BY_KEY,
    FEATURE_TOGGLES,
    FRONTEND_PATH_TO_MODULE,
    RESOURCE_PROFILES,
    SETTINGS_TAB_TO_MODULE,
    FeatureToggleService,
)

NEW_APP = ("nodes", "panel_ops")
NEW_BG = (
    "node_health",
    "cert_sync",
    "resource_metrics",
    "panel_resource_metrics",
    "cidr_scheduler",
    "node_sync_reconcile",
    "retention",
    "key_rotation",
    "user_reminders",
    "alert_rules",
    "noc_reports",
    "cloudflare_ips_update",
    "access_expiry",
    "connection_history",
)
ALWAYS_ON_FORBIDDEN = {"modules", "personal", "auth", "dashboard", "configurations"}


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    return path


def test_new_keys_registered_unique_and_defaults():
    keys = [item.key for item in FEATURE_TOGGLES]
    assert len(keys) == len(set(keys))
    env_keys = [item.env_key for item in FEATURE_TOGGLES]
    assert len(env_keys) == len(set(env_keys))
    for key in NEW_APP + NEW_BG:
        assert key in FEATURE_TOGGLE_BY_KEY
        item = FEATURE_TOGGLE_BY_KEY[key]
        if key == "cloudflare_ips_update":
            assert item.default is False
        else:
            assert item.default is True
        assert key not in ALWAYS_ON_FORBIDDEN


def test_nodes_and_panel_ops_bindings():
    assert FRONTEND_PATH_TO_MODULE["/nodes"] == "nodes"
    assert SETTINGS_TAB_TO_MODULE["panel_ops"] == "panel_ops"
    assert FEATURE_TOGGLE_BY_KEY["nodes"].group == "app_module"
    assert FEATURE_TOGGLE_BY_KEY["panel_ops"].group == "app_module"
    assert FEATURE_TOGGLE_BY_KEY["node_health"].group == "background"


def test_missing_env_defaults_on(env_file: Path):
    svc = FeatureToggleService(env_file)
    assert svc.is_enabled("nodes") is True
    assert svc.is_enabled("access_expiry") is True
    assert svc.is_enabled("cloudflare_ips_update") is False


def test_env_keys_match_existing_settings_where_applicable():
    assert FEATURE_TOGGLE_BY_KEY["node_health"].env_key == "NODE_HEALTH_SYNC_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["cert_sync"].env_key == "CERT_SYNC_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["resource_metrics"].env_key == "RESOURCE_METRICS_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["panel_resource_metrics"].env_key == "PANEL_RESOURCE_METRICS_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["cidr_scheduler"].env_key == "CIDR_DB_REFRESH_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["node_sync_reconcile"].env_key == "NODE_SYNC_RECONCILE_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["retention"].env_key == "RETENTION_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["user_reminders"].env_key == "SELF_SERVICE_REMINDER_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["alert_rules"].env_key == "ALERT_RULES_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["noc_reports"].env_key == "NOC_REPORT_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["cloudflare_ips_update"].env_key == "CLOUDFLARE_IPS_AUTO_UPDATE"
    assert FEATURE_TOGGLE_BY_KEY["key_rotation"].env_key == "FEATURE_KEY_ROTATION_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["access_expiry"].env_key == "FEATURE_ACCESS_EXPIRY_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["connection_history"].env_key == "FEATURE_CONNECTION_HISTORY_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["nodes"].env_key == "FEATURE_NODES_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["panel_ops"].env_key == "FEATURE_PANEL_OPS_ENABLED"


def test_resource_profiles_cover_new_background_keys():
    for profile_key, meta in RESOURCE_PROFILES.items():
        toggles = meta["toggles"]
        for key in NEW_BG:
            assert key in toggles, f"{profile_key} missing {key}"
        if profile_key == "minimal":
            assert toggles["node_health"] is False
            assert toggles["cert_sync"] is False
            assert toggles["resource_metrics"] is False
            assert toggles["panel_resource_metrics"] is False
            assert toggles["cidr_scheduler"] is False
            assert toggles["node_sync_reconcile"] is False
            assert toggles["noc_reports"] is False
            assert toggles["alert_rules"] is False
            assert toggles["connection_history"] is False
            # keep safety-ish on
            assert toggles["retention"] is True
            assert toggles["access_expiry"] is True
            assert toggles["key_rotation"] is True
            assert toggles["user_reminders"] is False
            assert toggles["cloudflare_ips_update"] is False
        else:
            assert toggles["node_health"] is True
            assert toggles["resource_metrics"] is True
            assert toggles["cidr_scheduler"] is (profile_key == "full")
