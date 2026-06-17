"""Tests for WARPER controller API."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth import get_password_hash
from app.config import Settings
from app.database import Base, get_db
from app.main import app
from app.models import Node, NodeStatus, User, UserRole


@pytest.fixture()
def warper_api_client(tmp_path):
    db_path = tmp_path / "test.db"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    admin = User(
        username="az_admin",
        password_hash=get_password_hash("secret123"),
        role=UserRole.admin,
        is_active=True,
    )
    node = Node(
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    session.add_all([admin, node])
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

    mock_adapter = MagicMock()
    mock_adapter.get_warper_health.return_value = {
        "installed": True,
        "active": True,
        "version": "1.4.0",
        "conflict_antizapret_warp": False,
    }
    mock_adapter.get_warper_status.return_value = {"outbound_mode": "warp"}
    mock_adapter.get_warper_doctor.return_value = [{"check": "sing-box", "status": "ok"}]
    mock_adapter.warper_toggle.return_value = {"message": "toggled"}
    mock_adapter.get_warper_domains.return_value = [{"domain": "example.com"}]
    mock_adapter.get_warper_domain_lists.return_value = {"gemini": False, "chatgpt": False}
    mock_adapter.get_warper_user_domains_text.return_value = "# Пользовательские домены:\nexample.com\n"
    mock_adapter.add_warper_domain.return_value = {"message": "added"}
    mock_adapter.remove_warper_domain.return_value = {"message": "removed"}
    mock_adapter.sync_warper_domains.return_value = {"message": "synced"}

    with (
        patch("app.config.get_settings", return_value=test_settings),
        patch("app.routers.warper.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.warper.get_active_node", return_value=node),
        patch("app.services.auth_rate_limit.get_settings", return_value=test_settings),
        patch("app.services.ip_restriction.ip_restriction_service.login_needs_captcha", return_value=False),
        patch("app.services.ip_restriction.ip_restriction_service.record_login_attempt", return_value=0),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.check", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_failure", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_success", return_value=None),
    ):
        client = TestClient(app)
        login = client.post("/api/auth/login/json", json={"username": "az_admin", "password": "secret123"})
        assert login.status_code == 200
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        yield client, headers, mock_adapter, node

    app.dependency_overrides.clear()
    session.close()


def test_api_get_warper_health(warper_api_client):
    client, headers, mock_adapter, node = warper_api_client
    response = client.get("/api/warper/health", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["installed"] is True
    assert data["node_id"] == node.id
    assert data["node_name"] == node.name
    mock_adapter.get_warper_health.assert_called_once()


def test_api_get_warper_domains(warper_api_client):
    client, headers, mock_adapter, _node = warper_api_client
    response = client.get("/api/warper/domains", headers=headers)
    assert response.status_code == 200
    assert response.json()["domains"][0]["domain"] == "example.com"
    assert response.json()["user_text"] == "# Пользовательские домены:\nexample.com\n"
    mock_adapter.get_warper_domains.assert_called_once()
    mock_adapter.get_warper_user_domains_text.assert_called_once()


def test_api_post_warper_domain(warper_api_client):
    client, headers, mock_adapter, _node = warper_api_client
    response = client.post("/api/warper/domains", headers=headers, json={"domain": "test.com"})
    assert response.status_code == 200
    mock_adapter.add_warper_domain.assert_called_once_with("test.com")


def test_api_sync_warper_domains(warper_api_client):
    client, headers, mock_adapter, _node = warper_api_client
    response = client.post("/api/warper/domains/sync", headers=headers)
    assert response.status_code == 200
    mock_adapter.sync_warper_domains.assert_called_once()


def test_api_warper_requires_auth(warper_api_client):
    client, _headers, _mock_adapter, _node = warper_api_client
    response = client.get("/api/warper/health")
    assert response.status_code == 401


def test_feature_guard_blocks_warper_api(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_WARPER_ENABLED=false\n", encoding="utf-8")

    def factory():
        return __import__(
            "app.services.feature_toggles", fromlist=["FeatureToggleService"]
        ).FeatureToggleService(env_file)

    monkeypatch.setattr("app.services.feature_guards.get_feature_service", factory)
    monkeypatch.setattr("app.routers.feature_toggles.get_feature_service", factory)

    from app.main import app as test_app

    client = TestClient(test_app)
    resp = client.get("/api/warper/health")
    assert resp.status_code == 403
    assert resp.json()["feature_disabled"] == "warper"
