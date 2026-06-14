"""Telegram settings API and user telegram_id updates (Phase 0)."""

import hashlib
import hmac
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import get_password_hash
from app.models import AppSetting, User, UserRole


def _client(env):
    return TestClient(env["app"])


def test_get_telegram_settings_defaults(api_test_env):
    response = _client(api_test_env).get("/api/settings/telegram", headers=api_test_env["admin_headers"])
    assert response.status_code == 200
    payload = response.json()
    assert payload["bot_token_set"] is False
    assert payload["bot_username"] == ""
    assert payload["auth_max_age_seconds"] == 300
    assert payload["mini_app_url"].endswith("/api/tg-mini")
    assert payload["notify_on_backup"] is False
    assert payload["interactive_enabled"] is False
    assert payload["webhook_registered"] is False


def test_patch_telegram_interactive_enabled(api_test_env):
    response = _client(api_test_env).patch(
        "/api/settings/telegram",
        json={"bot_token": "123:ABC", "interactive_enabled": True},
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["interactive_enabled"] is True
    assert payload["webhook_secret_set"] is True


def test_patch_telegram_settings_username_and_max_age(api_test_env):
    response = _client(api_test_env).patch(
        "/api/settings/telegram",
        json={
            "bot_token": "123456:ABC",
            "bot_username": "@mybot",
            "auth_max_age_seconds": 600,
            "notify_on_backup": True,
        },
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["bot_token_set"] is True
    assert payload["bot_username"] == "mybot"
    assert payload["auth_max_age_seconds"] == 600
    assert payload["notify_on_backup"] is True


def test_patch_telegram_settings_triggers_admin_notify(api_test_env):
    with patch("app.routers.maintenance.admin_notify_service.send_settings_change") as notify:
        response = _client(api_test_env).patch(
            "/api/settings/telegram",
            json={"bot_username": "notifybot"},
            headers=api_test_env["admin_headers"],
        )
    assert response.status_code == 200
    notify.assert_called_once()
    assert notify.call_args.kwargs["settings_key"] == "settings_telegram_auth_update"


def test_user_update_rejects_duplicate_telegram_id(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        other = User(
            username="tg_other",
            password_hash=get_password_hash("secret123"),
            role=UserRole.user,
            is_active=True,
            telegram_id="777001",
        )
        session.add(other)
        session.commit()
        admin = session.query(User).filter(User.username == "api_admin").first()
        admin_id = admin.id
    finally:
        session.close()

    response = _client(api_test_env).patch(
        f"/api/users/{admin_id}",
        json={"telegram_id": "777001"},
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 400


def test_user_update_accepts_valid_telegram_id(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        admin = session.query(User).filter(User.username == "api_admin").first()
        admin_id = admin.id
    finally:
        session.close()

    response = _client(api_test_env).patch(
        f"/api/users/{admin_id}",
        json={"telegram_id": "555001"},
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 200
    assert response.json()["telegram_id"] == "555001"


def test_user_update_clears_telegram_id(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        user = session.query(User).filter(User.username == "api_viewer").first()
        user.telegram_id = "888001"
        session.commit()
        user_id = user.id
    finally:
        session.close()

    response = _client(api_test_env).patch(
        f"/api/users/{user_id}",
        json={"telegram_id": ""},
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 200
    assert response.json()["telegram_id"] is None


def test_telegram_login_callback_redirects_with_token(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        admin = session.query(User).filter(User.username == "api_admin").first()
        admin.telegram_id = "3520910868"
        session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
        session.commit()
    finally:
        session.close()

    auth_date = str(int(time.time()))
    payload = {
        "id": "3520910868",
        "first_name": "Alex",
        "username": "Claymore0098",
        "auth_date": auth_date,
    }
    data_check_string = "\n".join(f"{k}={payload[k]}" for k in sorted(payload.keys()))
    secret_key = hashlib.sha256("test-bot-token".encode("utf-8")).digest()
    payload["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    response = _client(api_test_env).get("/api/auth/telegram", params=payload, follow_redirects=False)
    assert response.status_code in (302, 308)
    if response.status_code == 302:
        assert response.headers["location"].startswith("/login#token=")
        assert len(response.headers["location"]) > len("/login#token=")
