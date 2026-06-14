"""Tests for Telegram module shutdown and outbound guards."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models import AppSetting
from app.services.telegram_module import shutdown_telegram_integration


def test_shutdown_telegram_integration(db_session):
    db = db_session
    db.add(AppSetting(key="telegram_bot_token", value="123:ABC"))
    db.add(AppSetting(key="telegram_bot_interactive_enabled", value="true"))
    db.add(AppSetting(key="telegram_notify_enabled", value="true"))
    db.add(AppSetting(key="backup_telegram_enabled", value="true"))
    db.add(AppSetting(key="telegram_webhook_set_at", value="2026-01-01T00:00:00+00:00"))
    db.commit()

    with patch("app.services.telegram_module.delete_webhook_sync") as delete_webhook:
        result = shutdown_telegram_integration(db)
        delete_webhook.assert_called_once_with("123:ABC")

    assert result["webhook_deleted"] is True
    settings = {row.key: row.value for row in db.query(AppSetting).all()}
    assert settings["telegram_bot_interactive_enabled"] == "false"
    assert settings["telegram_notify_enabled"] == "false"
    assert settings["backup_telegram_enabled"] == "false"
    assert settings["telegram_webhook_set_at"] == ""
    assert settings["telegram_bot_token"] == "123:ABC"


def test_send_tg_message_skipped_when_module_disabled(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_TELEGRAM_ENABLED=false\n", encoding="utf-8")

    from app.services.feature_toggles import FeatureToggleService

    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: FeatureToggleService(env_file),
    )

    from app.services.telegram import send_tg_message

    with patch("app.services.telegram.threading.Thread") as thread_cls:
        ok = send_tg_message("123:ABC", "1", "hello", run_async=False)
        assert ok is False
        thread_cls.assert_not_called()


def test_settings_telegram_blocked_when_module_disabled(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_TELEGRAM_ENABLED=false\n", encoding="utf-8")

    from app.services.feature_toggles import FeatureToggleService

    service = FeatureToggleService(env_file)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", lambda: service)
    monkeypatch.setattr("app.routers.feature_toggles.get_feature_service", lambda: service)

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/settings/telegram")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "telegram"


def test_disable_telegram_via_feature_toggle(api_test_env):
    env = api_test_env
    features_env = env["tmp_path"] / "features.env"
    from app.services.feature_toggles import FeatureToggleService

    service = FeatureToggleService(features_env)
    assert service.is_enabled("telegram") is True

    session = env["session_factory"]()
    try:
        session.add(AppSetting(key="telegram_bot_token", value="123:ABC"))
        session.add(AppSetting(key="telegram_bot_interactive_enabled", value="true"))
        session.commit()
    finally:
        session.close()

    from fastapi.testclient import TestClient

    client = TestClient(env["app"])
    with patch("app.services.telegram_module.delete_webhook_sync") as delete_webhook:
        resp = client.put(
            "/api/feature-toggles",
            headers=env["admin_headers"],
            json={"toggles": {"telegram": False}},
        )
        assert resp.status_code == 200
        delete_webhook.assert_called_once_with("123:ABC")

    assert FeatureToggleService(features_env).is_enabled("telegram") is False
