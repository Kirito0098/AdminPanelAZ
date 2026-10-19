"""Stage 5 Task 1-3: scenario presets (panel_only / home / commercial).

TDD: data + label mapping (Task 1), service get/list/preview/apply/resolve (Task 2),
upgrade migration «label only» (Task 3), CLI smoke (Task 5).
"""

from pathlib import Path

import pytest

from app.services.feature_toggles import (
    LEGACY_RESOURCE_PROFILE_TO_SCENARIO,
    SCENARIO_PRESETS,
    VALID_SCENARIO_PRESETS,
    FeatureToggleService,
    map_legacy_resource_profile,
)


def test_valid_scenario_keys():
    assert VALID_SCENARIO_PRESETS == frozenset({"panel_only", "home", "commercial"})
    assert set(SCENARIO_PRESETS) == VALID_SCENARIO_PRESETS


def test_legacy_profile_label_map():
    assert LEGACY_RESOURCE_PROFILE_TO_SCENARIO == {
        "minimal": "panel_only",
        "standard": "home",
        "full": "commercial",
    }
    assert map_legacy_resource_profile("minimal") == "panel_only"
    assert map_legacy_resource_profile("FULL") == "commercial"
    assert map_legacy_resource_profile("unknown") is None


def test_spec_table_toggle_matrix():
    """§8.2 table — keys that must match exactly."""
    expected = {
        "panel_only": {
            "clients_page": True,
            "user_provisioning": False,
            "unlock_codes": False,
            "client_portal": False,
            "traffic_sync": False,
            "noc_reports": False,
            "alert_rules": False,
            "warper": False,
            "server_monitor": False,
            "telegram": False,
            "proxy_nodes": False,
            "node_sync_reconcile": False,
            "cloudflare_ips_update": False,
            "edit_files": True,
            "node_ssh_transport": True,
            "server_resources": False,
        },
        "home": {
            "clients_page": True,
            "user_provisioning": False,
            "unlock_codes": False,
            "client_portal": False,
            "traffic_sync": False,
            "noc_reports": False,
            "alert_rules": False,
            "warper": False,
            "server_monitor": True,
            "telegram": True,
            "proxy_nodes": True,
            "node_sync_reconcile": True,
            "cloudflare_ips_update": True,
            "edit_files": True,
            "node_ssh_transport": True,
            "server_resources": True,
        },
        "commercial": {
            "clients_page": True,
            "user_provisioning": True,
            "unlock_codes": True,
            "client_portal": True,
            "traffic_sync": True,
            "noc_reports": True,
            "alert_rules": True,
            "warper": True,
            "server_monitor": True,
            "telegram": True,
            "proxy_nodes": True,
            "node_sync_reconcile": True,
            "cloudflare_ips_update": True,
            "edit_files": True,
            "node_ssh_transport": True,
            "server_resources": True,
        },
    }
    for key, want in expected.items():
        toggles = SCENARIO_PRESETS[key]["toggles"]
        for tkey, val in want.items():
            assert toggles[tkey] is val, f"{key}.{tkey}"


def test_grace_and_workers_from_spec():
    assert SCENARIO_PRESETS["panel_only"]["settings"]["inactive_user_grace_period_months"] == 0
    assert SCENARIO_PRESETS["home"]["settings"]["inactive_user_grace_period_months"] == 0
    assert SCENARIO_PRESETS["commercial"]["settings"]["inactive_user_grace_period_months"] == 3
    assert set(SCENARIO_PRESETS["panel_only"]["workers_disabled"]) == {
        "traffic_collector",
        "node_health",
        "resource_metrics",
        "panel_resource_metrics",
        "cidr_scheduler",
        "cert_sync",
        "resource_monitor",
    }
    assert SCENARIO_PRESETS["home"]["workers_disabled"] == ["cidr_scheduler"]
    assert SCENARIO_PRESETS["commercial"]["workers_disabled"] == []


def test_env_writes_scenario_preset_key():
    for key, meta in SCENARIO_PRESETS.items():
        assert meta["env"]["SCENARIO_PRESET"] == key
        assert "RESOURCE_PROFILE" not in meta["env"]


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text("SCENARIO_PRESET=home\nFEATURE_TELEGRAM_ENABLED=false\n", encoding="utf-8")
    return path


def test_apply_writes_scenario_and_removes_legacy(env_file: Path):
    env_file.write_text(
        "RESOURCE_PROFILE=full\nFEATURE_TELEGRAM_ENABLED=false\nTRAFFIC_SYNC_ENABLED=true\n",
        encoding="utf-8",
    )
    svc = FeatureToggleService(env_file)
    result = svc.apply_scenario_preset("panel_only")
    text = env_file.read_text(encoding="utf-8")
    assert "SCENARIO_PRESET=panel_only" in text
    assert "RESOURCE_PROFILE=" not in text
    assert result["preset"] == "panel_only"
    assert svc.is_enabled("traffic_sync") is False


def test_preview_lists_enable_and_disable(env_file: Path):
    env_file.write_text(
        "SCENARIO_PRESET=home\n"
        "FEATURE_TELEGRAM_ENABLED=false\n"
        "FEATURE_SERVER_MONITOR_ENABLED=true\n",
        encoding="utf-8",
    )
    svc = FeatureToggleService(env_file)
    preview = svc.preview_scenario_preset("commercial")
    assert "telegram" in preview["will_enable_keys"] or any(
        "Telegram" in x for x in preview["will_enable"]
    )
    assert "will_disable" in preview


def test_resolve_custom_when_toggles_diverge(env_file: Path):
    svc = FeatureToggleService(env_file)
    svc.apply_scenario_preset("home")
    # Flip one toggle away from home
    telegram_def = __import__(
        "app.services.feature_toggles", fromlist=["FEATURE_TOGGLE_BY_KEY"]
    ).FEATURE_TOGGLE_BY_KEY["telegram"]
    svc.env.set_env_value(telegram_def.env_key, "false" if svc.is_enabled("telegram") else "true")
    svc._invalidate_env_map()
    state = svc.resolve_scenario_state()
    assert state["is_custom"] is True
    assert state["based_on"] == "home"
    assert state["changed_count"] >= 1
    assert "Кастомный" in state["badge_label"]


def test_migrate_renames_label_without_touching_toggles(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "RESOURCE_PROFILE=minimal\n"
        "TRAFFIC_SYNC_ENABLED=true\n"
        "FEATURE_TELEGRAM_ENABLED=true\n",
        encoding="utf-8",
    )
    svc = FeatureToggleService(env)
    assert svc.migrate_resource_profile_label_only() is True
    text = env.read_text(encoding="utf-8")
    assert "SCENARIO_PRESET=panel_only" in text
    assert "RESOURCE_PROFILE=" not in text
    assert "TRAFFIC_SYNC_ENABLED=true" in text
    assert "FEATURE_TELEGRAM_ENABLED=true" in text
    # Must NOT have forced panel_only toggles
    assert "TRAFFIC_SYNC_ENABLED=false" not in text


def test_migrate_idempotent_when_scenario_already_set(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "SCENARIO_PRESET=home\nRESOURCE_PROFILE=full\nTRAFFIC_SYNC_ENABLED=true\n",
        encoding="utf-8",
    )
    svc = FeatureToggleService(env)
    assert svc.migrate_resource_profile_label_only() is True  # still drops legacy key
    assert svc.migrate_resource_profile_label_only() is False
    text = env.read_text(encoding="utf-8")
    assert "SCENARIO_PRESET=home" in text
    assert "RESOURCE_PROFILE=" not in text
    assert "TRAFFIC_SYNC_ENABLED=true" in text


def test_migrate_noop_without_legacy(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("SCENARIO_PRESET=commercial\n", encoding="utf-8")
    svc = FeatureToggleService(env)
    assert svc.migrate_resource_profile_label_only() is False


def test_cli_apply_scenario_preset(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    import runpy
    import sys
    argv = ["apply-scenario-preset.py", "panel_only", "--env", str(env)]
    old = sys.argv
    sys.argv = argv
    try:
        runpy.run_path(
            str(Path(__file__).resolve().parents[2] / "scripts" / "apply-scenario-preset.py"),
            run_name="__main__",
        )
    except SystemExit as exc:
        assert exc.code == 0
    finally:
        sys.argv = old
    assert "SCENARIO_PRESET=panel_only" in env.read_text(encoding="utf-8")
