"""Tests for AntiZapret setup settings (phase 6)."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth import get_password_hash
from app.config import Settings
from app.database import Base, get_db
from app.main import app
from app.models import Node, NodeStatus, User, UserRole
from app.services.antizapret_settings import (
    build_schema,
    filter_known_keys,
    is_openvpn_verbose_log_enabled,
    normalize_flag,
    read_antizapret_settings,
    update_antizapret_settings,
)


class TestAntizapretSettingsService:
    def test_read_antizapret_settings_from_fixture(self):
        content = "ROUTE_ALL=y\nDISCORD_INCLUDE=n\n"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        settings = read_antizapret_settings(tmp_path)
        assert settings.get("route_all") == "y"
        assert settings.get("discord_include") == "n"
        assert settings.get("telegram_include") == "n"

    def test_normalize_flag(self):
        assert normalize_flag(True) == "y"
        assert normalize_flag(False) == "n"
        assert normalize_flag("yes") == "y"
        assert normalize_flag("on") == "y"
        assert normalize_flag("1") == "y"
        assert normalize_flag("n") == "n"
        assert normalize_flag("false") == "n"

    def test_update_preserves_comments(self, tmp_path: Path):
        setup = tmp_path / "setup"
        setup.write_text("ROUTE_ALL=n  # keep this comment\nOTHER=value\n", encoding="utf-8")
        result = update_antizapret_settings(setup, {"route_all": "y"})
        assert result["changes"] == 1
        assert result["needs_apply"] is True
        text = setup.read_text(encoding="utf-8")
        assert "ROUTE_ALL=y keep this comment" in text
        assert "OTHER=value" in text

    def test_partial_update_only_passed_keys(self, tmp_path: Path):
        setup = tmp_path / "setup"
        setup.write_text("ROUTE_ALL=n\nDISCORD_INCLUDE=y\n", encoding="utf-8")
        result = update_antizapret_settings(setup, {"route_all": True})
        assert result["changes"] == 1
        settings = read_antizapret_settings(setup)
        assert settings["route_all"] == "y"
        assert settings["discord_include"] == "y"

    def test_empty_update_returns_no_changes(self, tmp_path: Path):
        setup = tmp_path / "setup"
        setup.write_text("ROUTE_ALL=n\n", encoding="utf-8")
        result = update_antizapret_settings(setup, {})
        assert result["changes"] == 0
        assert result["needs_apply"] is False
        assert result["message"] == "Нечего обновлять"

    def test_append_missing_key(self, tmp_path: Path):
        setup = tmp_path / "setup"
        setup.write_text("# comment only\n", encoding="utf-8")
        result = update_antizapret_settings(setup, {"route_all": "y"})
        assert result["changes"] == 1
        assert read_antizapret_settings(setup)["route_all"] == "y"

    def test_is_openvpn_verbose_log_enabled(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
            tmp.write("OPENVPN_LOG=n\n")
            disabled_path = Path(tmp.name)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
            tmp.write("OPENVPN_LOG=y\n")
            enabled_path = Path(tmp.name)

        assert is_openvpn_verbose_log_enabled(disabled_path) is False
        assert is_openvpn_verbose_log_enabled(enabled_path) is True
        assert is_openvpn_verbose_log_enabled(Path("/nonexistent/setup")) is False

    def test_filter_known_keys(self):
        filtered = filter_known_keys({"route_all": "y", "unknown_key": "x"})
        assert filtered == {"route_all": "y"}

    def test_build_schema_has_all_params(self):
        schema = build_schema()
        assert len(schema) == 20
        assert schema[0]["key"] == "route_all"
        assert schema[0]["type"] == "flag"


@pytest.fixture()
def antizapret_api_client(tmp_path):
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
    mock_adapter.get_antizapret_settings.return_value = {"route_all": "n", "discord_include": "y"}
    mock_adapter.update_antizapret_settings.return_value = {
        "success": True,
        "message": "Настройки сохранены",
        "changes": 1,
        "needs_apply": True,
    }

    with (
        patch("app.config.get_settings", return_value=test_settings),
        patch("app.routers.routing.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.routing.get_active_node", return_value=node),
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


def test_api_get_antizapret_settings(antizapret_api_client):
    client, headers, mock_adapter, node = antizapret_api_client
    response = client.get("/api/routing/antizapret-settings", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["settings"]["route_all"] == "n"
    assert len(data["schema"]) == 20
    assert data["node_id"] == node.id
    assert data["node_name"] == node.name
    mock_adapter.get_antizapret_settings.assert_called_once()


def test_api_put_antizapret_settings(antizapret_api_client):
    client, headers, mock_adapter, _node = antizapret_api_client
    response = client.put(
        "/api/routing/antizapret-settings",
        headers=headers,
        json={"route_all": True, "unknown": "skip"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["changes"] == 1
    assert data["needs_apply"] is True
    mock_adapter.update_antizapret_settings.assert_called_once_with({"route_all": True})


def test_api_put_requires_auth(antizapret_api_client):
    client, _headers, _mock_adapter, _node = antizapret_api_client
    response = client.put("/api/routing/antizapret-settings", json={"route_all": "y"})
    assert response.status_code == 401


def test_feature_guard_blocks_antizapret_settings(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_ROUTING_ENABLED=false\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: __import__(
            "app.services.feature_toggles", fromlist=["FeatureToggleService"]
        ).FeatureToggleService(env_file),
    )
    client = TestClient(app)
    response = client.get("/api/routing/antizapret-settings")
    assert response.status_code == 403
    assert response.json()["feature_disabled"] == "routing"
