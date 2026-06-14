"""Feature toggle service tests (subset ported from AdminAntizapret)."""

from pathlib import Path

from app.services.feature_toggles import FEATURE_TOGGLES, FeatureToggleService


def test_get_feature_states_defaults_true(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    service = FeatureToggleService(env_file)
    states = service.get_feature_states()
    for item in FEATURE_TOGGLES:
        expected = item.default
        assert states[item.key] is expected, item.key


def test_is_enabled_reads_env(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("MONITOR_ENABLED=false\n", encoding="utf-8")
    service = FeatureToggleService(env_file)
    assert service.is_enabled("resource_monitor") is False


def test_get_app_module_states_only_app_modules(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_ROUTING_ENABLED=false\n", encoding="utf-8")
    service = FeatureToggleService(env_file)
    states = service.get_app_module_states()
    assert states["routing"] is False
    assert states["openvpn"] is True
    assert "traffic_sync" not in states


def test_update_toggles_persists(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    service = FeatureToggleService(env_file)
    result = service.update_toggles({"routing": False})
    assert result["disabled_count"] >= 1
    reloaded = FeatureToggleService(env_file)
    assert reloaded.is_enabled("routing") is False
