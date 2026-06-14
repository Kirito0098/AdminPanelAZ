"""Shared pytest configuration and fixtures for AdminPanelAZ backend tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_async(coro):
    """Run an async coroutine from sync pytest tests."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _neutralize_deploy_env(monkeypatch):
    """Production .env often sets ENFORCE_HTTPS/BEHIND_NGINX; keep HTTP tests stable."""
    from app.config import get_settings

    monkeypatch.setenv("ENFORCE_HTTPS", "false")
    monkeypatch.setenv("BEHIND_NGINX", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db_session(tmp_path):
    """Isolated SQLite session for unit tests that need AppSetting rows."""
    from app.database import Base

    db_path = tmp_path / "unit_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def async_client():
    from app.main import app

    transport = ASGITransport(app=app)

    async def _request(method: str, url: str, **kwargs):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url, **kwargs)

    return _request


@pytest.fixture()
def api_test_env(tmp_path, monkeypatch):
    """Isolated SQLite DB + patched auth/rate-limit for API integration tests."""
    from app.auth import create_access_token, get_password_hash
    from app.config import Settings
    from app.database import Base, get_db
    from app.main import app
    from app.models import Node, NodeStatus, User, UserRole

    db_path = tmp_path / "api_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    admin = User(
        username="api_admin",
        password_hash=get_password_hash("secret123"),
        role=UserRole.admin,
        is_active=True,
    )
    viewer = User(
        username="api_viewer",
        password_hash=get_password_hash("secret123"),
        role=UserRole.viewer,
        is_active=True,
    )
    node = Node(
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    session.add_all([admin, viewer, node])
    session.commit()

    test_settings = Settings(
        app_env="development",
        enforce_password_policy=False,
        auth_rate_limit_enabled=False,
        api_rate_limit_enabled=False,
        audit_log_enabled=False,
        security_headers_enabled=True,
        enforce_https=False,
        behind_nginx=False,
    )

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    mock_adapter = MagicMock()
    mock_adapter.read_config_file.return_value = ""
    mock_adapter.write_config_file.return_value = None
    mock_adapter.apply_config_changes.return_value = "ok"
    mock_adapter.ensure_openvpn_ban_check.return_value = None

    from app.services.feature_toggles import FEATURE_TOGGLES, FeatureToggleService

    features_env = tmp_path / "features.env"
    features_env.write_text(
        "\n".join(f"{item.env_key}=true" for item in FEATURE_TOGGLES) + "\n",
        encoding="utf-8",
    )
    feature_service = FeatureToggleService(features_env)

    patches = (
        patch("app.config.get_settings", return_value=test_settings),
        patch("app.middleware.http_security.get_settings", return_value=test_settings),
        patch("app.routers.maintenance.get_settings", return_value=test_settings),
        patch("app.services.api_rate_limit.get_settings", return_value=test_settings),
        patch("app.services.public_download_rate_limit.get_settings", return_value=test_settings),
        patch("app.services.ip_restriction.ip_restriction_service.login_needs_captcha", return_value=False),
        patch("app.services.ip_restriction.ip_restriction_service.record_login_attempt", return_value=0),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.check", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_failure", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_success", return_value=None),
        patch("app.services.feature_guards.get_feature_service", return_value=feature_service),
        patch("app.routers.feature_toggles.get_feature_service", return_value=feature_service),
        patch("app.routers.edit_files.get_active_adapter", return_value=mock_adapter),
        patch("app.services.node_manager.get_active_adapter", return_value=mock_adapter),
    )
    for item in patches:
        item.start()

    admin_token = create_access_token({"sub": admin.username, "role": admin.role.value})
    viewer_token = create_access_token({"sub": viewer.username, "role": viewer.role.value})

    yield {
        "app": app,
        "session_factory": TestingSession,
        "node": node,
        "mock_adapter": mock_adapter,
        "admin_headers": {"Authorization": f"Bearer {admin_token}"},
        "viewer_headers": {"Authorization": f"Bearer {viewer_token}"},
        "settings": test_settings,
        "tmp_path": tmp_path,
    }

    for item in reversed(patches):
        item.stop()
    app.dependency_overrides.clear()
    session.close()
