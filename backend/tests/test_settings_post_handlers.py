"""Settings validation for backups and Telegram (ported from AdminAntizapret settings_post_handlers)."""

from fastapi.testclient import TestClient

from app.auth import get_password_hash
from app.models import User, UserRole


def _client(env):
    return TestClient(env["app"])


def test_backup_settings_update_persists(api_test_env):
    response = _client(api_test_env).patch(
        "/api/backups/settings",
        json={
            "auto_backup_enabled": True,
            "auto_backup_days": 7,
            "telegram_on_backup": True,
            "retention_count": 5,
        },
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["auto_backup_enabled"] is True
    assert payload["auto_backup_days"] == 7
    assert payload["telegram_on_backup"] is True
    assert payload["retention_count"] == 5


def test_backup_settings_rejects_invalid_days(api_test_env):
    response = _client(api_test_env).patch(
        "/api/backups/settings",
        json={"auto_backup_days": 0},
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 422


def test_telegram_settings_rejects_duplicate_id(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        other = User(
            username="other_admin",
            password_hash=get_password_hash("secret123"),
            role=UserRole.admin,
            is_active=True,
            telegram_id="555001",
        )
        session.add(other)
        session.commit()
    finally:
        session.close()

    response = _client(api_test_env).patch(
        "/api/settings/admin-notify",
        json={"telegram_id": "555001"},
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 400


def test_telegram_settings_accepts_valid_id(api_test_env):
    response = _client(api_test_env).patch(
        "/api/settings/admin-notify",
        json={"telegram_id": "123456789"},
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 200
    assert response.json()["telegram_id"] == "123456789"
