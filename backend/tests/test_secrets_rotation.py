"""Secrets rotation wizard API (Idei.md 9.4)."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import get_password_hash
from app.config import Settings, get_settings
from app.models import AppSetting, Node, User
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.secrets_rotation import SecretsRotationService


def _client(env):
    return TestClient(env["app"])


def test_list_secrets_rotation(api_test_env):
    response = _client(api_test_env).get("/api/security/secrets-rotation", headers=api_test_env["admin_headers"])
    assert response.status_code == 200
    items = response.json()
    ids = {item["secret_id"] for item in items}
    assert ids == {"secret_key", "node_agent_api_key", "telegram_bot_token"}


def test_list_secrets_rotation_forbidden_for_viewer(api_test_env):
    response = _client(api_test_env).get("/api/security/secrets-rotation", headers=api_test_env["viewer_headers"])
    assert response.status_code == 403


def test_preview_and_apply_secret_key(api_test_env, monkeypatch, tmp_path):
    explicit_sk = "change-me-in-production-use-long-random-string"
    api_test_env["settings"].secret_key = explicit_sk

    env_file = tmp_path / ".env"
    env_file.write_text(f"SECRET_KEY={explicit_sk}\n", encoding="utf-8")

    session = api_test_env["session_factory"]()
    try:
        remote = Node(
            name="remote",
            host="203.0.113.10",
            port=9100,
            is_local=False,
            api_key_encrypted=encrypt_secret("remote-node-key", explicit_sk),
        )
        session.add(remote)
        session.commit()
        remote_id = remote.id
    finally:
        session.close()

    monkeypatch.setenv("SECRET_KEY", explicit_sk)
    get_settings.cache_clear()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.secrets_rotation._panel_env_path", lambda: env_file)

        preview = _client(api_test_env).post(
            "/api/security/secrets-rotation/preview",
            json={"secret_id": "secret_key"},
            headers=api_test_env["admin_headers"],
        )
        assert preview.status_code == 200
        payload = preview.json()
        assert payload["requires_relogin"] is True
        assert "re-login" in " ".join(payload["warnings"]).lower() or "JWT" in " ".join(payload["warnings"])
        assert payload["new_value"]
        assert payload["preview_token"]

        bad_confirm = _client(api_test_env).post(
            "/api/security/secrets-rotation/apply",
            json={
                "secret_id": "secret_key",
                "new_value": payload["new_value"],
                "preview_token": payload["preview_token"],
                "confirm": "NOPE",
            },
            headers=api_test_env["admin_headers"],
        )
        assert bad_confirm.status_code == 400

        apply = _client(api_test_env).post(
            "/api/security/secrets-rotation/apply",
            json={
                "secret_id": "secret_key",
                "new_value": payload["new_value"],
                "preview_token": payload["preview_token"],
                "confirm": "ROTATE",
            },
            headers=api_test_env["admin_headers"],
        )
        assert apply.status_code == 200
        result = apply.json()
        assert result["requires_relogin"] is True
        assert result["reencrypt_stats"]["errors"] == 0
        assert result["reencrypt_stats"]["nodes"] == 1

    written = env_file.read_text(encoding="utf-8")
    assert "SECRET_KEY=" in written
    assert "change-me-in-production-use-long-random-string" not in written

    session = api_test_env["session_factory"]()
    try:
        node = session.query(Node).filter(Node.id == remote_id).first()
        assert decrypt_secret(node.api_key_encrypted, payload["new_value"]) == "remote-node-key"
    finally:
        session.close()


def test_preview_telegram_token_requires_value(api_test_env):
    response = _client(api_test_env).post(
        "/api/security/secrets-rotation/preview",
        json={"secret_id": "telegram_bot_token"},
        headers=api_test_env["admin_headers"],
    )
    assert response.status_code == 400


def test_apply_telegram_token_to_db(api_test_env):
    token = "123456789:ABCDEFghijklmnopqrstuvwxyz123456"
    preview = _client(api_test_env).post(
        "/api/security/secrets-rotation/preview",
        json={"secret_id": "telegram_bot_token", "value": token},
        headers=api_test_env["admin_headers"],
    )
    assert preview.status_code == 200
    payload = preview.json()

    apply = _client(api_test_env).post(
        "/api/security/secrets-rotation/apply",
        json={
            "secret_id": "telegram_bot_token",
            "new_value": payload["new_value"],
            "preview_token": payload["preview_token"],
            "confirm": "ROTATE",
        },
        headers=api_test_env["admin_headers"],
    )
    assert apply.status_code == 200

    session = api_test_env["session_factory"]()
    try:
        row = session.query(AppSetting).filter(AppSetting.key == "telegram_bot_token").first()
        assert row is not None
        assert row.value == token
    finally:
        session.close()


def test_apply_node_agent_api_key_writes_env(api_test_env, monkeypatch, tmp_path):
    env_file = tmp_path / "node_agent.env"
    env_file.write_text("NODE_AGENT_API_KEY=change-me-node-agent-key\n", encoding="utf-8")
    monkeypatch.setenv("NODE_AGENT_ENV_FILE", str(env_file))

    preview = _client(api_test_env).post(
        "/api/security/secrets-rotation/preview",
        json={"secret_id": "node_agent_api_key"},
        headers=api_test_env["admin_headers"],
    )
    assert preview.status_code == 200
    payload = preview.json()

    apply = _client(api_test_env).post(
        "/api/security/secrets-rotation/apply",
        json={
            "secret_id": "node_agent_api_key",
            "new_value": payload["new_value"],
            "preview_token": payload["preview_token"],
            "confirm": "ROTATE",
        },
        headers=api_test_env["admin_headers"],
    )
    assert apply.status_code == 200
    written = env_file.read_text(encoding="utf-8")
    assert "NODE_AGENT_API_KEY=" in written
    assert "change-me-node-agent-key" not in written


def test_service_preview_rejects_same_value(api_test_env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=already-set-secret-key-32chars-min\n", encoding="utf-8")
    session = api_test_env["session_factory"]()
    service = SecretsRotationService()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.secrets_rotation._panel_env_path",
            lambda: env_file,
        )
        mp.setattr(
            "app.services.secrets_rotation.get_settings",
            lambda: Settings(
                app_env="development",
                secret_key="already-set-secret-key-32chars-min",
                auth_rate_limit_enabled=False,
                api_rate_limit_enabled=False,
            ),
        )
        with pytest.raises(ValueError, match="совпадает"):
            service.preview(session, "secret_key", value="already-set-secret-key-32chars-min")
    session.close()
