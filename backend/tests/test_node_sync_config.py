"""HA auto-sync settings (config.py step 0.1)."""

from app.config import Settings, get_settings


def test_node_sync_settings_defaults():
    get_settings.cache_clear()
    try:
        settings = Settings()
        assert settings.node_sync_auto_replicate_config_files is True
        assert settings.node_sync_auto_replicate_policies is True
        assert settings.node_sync_auto_heal is False
        assert settings.node_sync_auto_heal_max_failures == 3
        assert settings.node_sync_replicate_doall is True
    finally:
        get_settings.cache_clear()
