"""Integration tests: login triggers AdminNotify when configured."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_password_hash
from app.config import Settings
from app.database import Base, get_db
from app.main import app
from app.models import AppSetting, DEFAULT_TG_NOTIFY_EVENTS, User, UserRole


@pytest.fixture()
def notify_client(tmp_path):
    db_path = tmp_path / "integration.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    admin = User(
        username="notify_admin",
        password_hash=get_password_hash("secret123"),
        role=UserRole.admin,
        is_active=True,
        telegram_id="900001",
        tg_notify_events=json.dumps({**DEFAULT_TG_NOTIFY_EVENTS, "login_success": True}),
    )
    viewer = User(
        username="notify_viewer",
        password_hash=get_password_hash("secret123"),
        role=UserRole.viewer,
        is_active=True,
        telegram_id="900002",
        tg_notify_events=json.dumps({**DEFAULT_TG_NOTIFY_EVENTS, "login_success": False}),
    )
    session.add_all([admin, viewer])
    session.add(AppSetting(key="telegram_bot_token", value="test-bot-token"))
    session.add(AppSetting(key="telegram_notify_enabled", value="true"))
    session.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    test_settings = Settings(
        app_env="development",
        enforce_password_policy=False,
        auth_rate_limit_enabled=False,
        audit_log_enabled=False,
    )

    sent: list[tuple] = []

    def _capture_send(token, chat_id, text, **kwargs):
        sent.append((token, chat_id, text))
        return True

    mock_feature = MagicMock()
    mock_feature.is_enabled.return_value = True

    with (
        patch("app.services.admin_notify.get_settings", return_value=test_settings),
        patch("app.config.get_settings", return_value=test_settings),
        patch("app.services.admin_notify.get_feature_service", return_value=mock_feature),
        patch("app.services.admin_notify.send_tg_message", side_effect=_capture_send),
        patch("app.services.auth_rate_limit.get_settings", return_value=test_settings),
        patch("app.services.ip_restriction.ip_restriction_service.login_needs_captcha", return_value=False),
        patch("app.services.ip_restriction.ip_restriction_service.record_login_attempt", return_value=0),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.check", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_failure", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_success", return_value=None),
    ):
        client = TestClient(app)
        yield client, sent, session

    app.dependency_overrides.clear()
    session.close()


def test_login_triggers_admin_notify(notify_client):
    client, sent, _session = notify_client
    response = client.post(
        "/api/auth/login/json",
        json={"username": "notify_admin", "password": "secret123"},
    )
    assert response.status_code == 200
    assert response.json().get("access_token")
    assert len(sent) == 1
    assert sent[0][0] == "test-bot-token"
    assert sent[0][1] == "900001"
    assert "Вход в панель" in sent[0][2]


def test_viewer_login_skips_admin_notify(notify_client):
    client, sent, _session = notify_client
    response = client.post(
        "/api/auth/login/json",
        json={"username": "notify_viewer", "password": "secret123"},
    )
    assert response.status_code == 200
    assert sent == []
