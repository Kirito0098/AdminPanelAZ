"""Tests for public route downloads, toggle and OpenVPN group (config_routes parity)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, get_password_hash
from app.database import Base, get_db
from app.main import app
from app.models import AppSetting, User, UserRole
from app.services.public_download_settings import set_public_download_enabled


@pytest.fixture()
def public_routes_client(tmp_path, monkeypatch):
    db_path = tmp_path / "public_routes.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    admin = User(
        username="routes_admin",
        password_hash=get_password_hash("secret123"),
        role=UserRole.admin,
        is_active=True,
    )
    user = User(
        username="routes_user",
        password_hash=get_password_hash("secret123"),
        role=UserRole.user,
        is_active=True,
    )
    session.add_all([admin, user])
    session.commit()

    env_file = tmp_path / ".env"
    env_file.write_text(
        "FEATURE_SECURITY_ENABLED=true\nFEATURE_OPENVPN_ENABLED=true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: __import__(
            "app.services.feature_toggles", fromlist=["FeatureToggleService"]
        ).FeatureToggleService(env_file),
    )

    mock_adapter = MagicMock()
    mock_adapter.get_route_result_content.return_value = {
        "key": "keenetic_wg",
        "filename": "keenetic-wireguard-routes.txt",
        "content": "10.0.0.0/8\n",
        "line_count": 1,
    }
    mock_adapter.get_profile_files.return_value = [
        {
            "protocol": "openvpn",
            "variant": "antizapret",
            "filename": "antizapret-test.ovpn",
            "path": "/tmp/antizapret-test.ovpn",
        },
        {
            "protocol": "openvpn",
            "variant": "antizapret-udp",
            "filename": "antizapret-test-udp.ovpn",
            "path": "/tmp/antizapret-test-udp.ovpn",
        },
    ]

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        "app.routers.public_download.get_active_adapter",
        lambda _db: mock_adapter,
    )
    monkeypatch.setattr(
        "app.routers.configs.get_active_adapter",
        lambda _db: mock_adapter,
    )

    client = TestClient(app)
    admin_token = create_access_token({"sub": admin.username, "role": admin.role.value})
    user_token = create_access_token({"sub": user.username, "role": user.role.value})

    yield client, TestingSession, admin_token, user_token, mock_adapter, env_file

    app.dependency_overrides.clear()
    session.close()


def test_public_route_download_disabled_returns_404(public_routes_client):
    client, session_factory, _, _, _, _ = public_routes_client
    db = session_factory()
    try:
        set_public_download_enabled(db, False)
    finally:
        db.close()

    response = client.get("/api/public/route-download/keenetic")
    assert response.status_code == 404


def test_public_route_download_serves_file(public_routes_client):
    client, session_factory, _, _, mock_adapter, _ = public_routes_client
    db = session_factory()
    try:
        set_public_download_enabled(db, True)
    finally:
        db.close()

    response = client.get("/api/public/route-download/keenetic")
    assert response.status_code == 200
    assert "keenetic-wireguard-routes.txt" in response.headers.get("content-disposition", "")
    assert "10.0.0.0/8" in response.text
    mock_adapter.get_route_result_content.assert_called_once_with("keenetic_wg")


def test_public_route_download_unknown_router_404(public_routes_client):
    client, session_factory, _, _, _, _ = public_routes_client
    db = session_factory()
    try:
        set_public_download_enabled(db, True)
    finally:
        db.close()

    response = client.get("/api/public/route-download/unknown")
    assert response.status_code == 404


def test_toggle_public_download(public_routes_client):
    client, session_factory, admin_token, _, _, _ = public_routes_client
    db = session_factory()
    try:
        set_public_download_enabled(db, False)
    finally:
        db.close()

    response = client.post(
        "/api/security/public-download",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"enabled": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True

    db = session_factory()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "public_download_enabled").first()
        assert row is not None
        assert row.value == "true"
    finally:
        db.close()


def test_set_openvpn_group_filters_profile_files(public_routes_client):
    client, session_factory, _, user_token, _, _ = public_routes_client

    response = client.put(
        "/api/configs/openvpn-group",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"group": "GROUP_UDP"},
    )
    assert response.status_code == 200
    assert response.json()["group"] == "GROUP_UDP"

    db = session_factory()
    try:
        user = db.query(User).filter(User.username == "routes_user").first()
        row = db.query(AppSetting).filter(AppSetting.key == f"openvpn_group:user:{user.id}").first()
        assert row is not None
        assert row.value == "GROUP_UDP"
    finally:
        db.close()


def test_public_route_download_blocked_when_security_disabled(public_routes_client, monkeypatch):
    client, session_factory, _, _, _, env_file = public_routes_client
    env_file.write_text(
        "FEATURE_SECURITY_ENABLED=false\nFEATURE_OPENVPN_ENABLED=true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: __import__(
            "app.services.feature_toggles", fromlist=["FeatureToggleService"]
        ).FeatureToggleService(env_file),
    )

    db = session_factory()
    try:
        set_public_download_enabled(db, True)
    finally:
        db.close()

    response = client.get("/api/public/route-download/keenetic")
    assert response.status_code == 403
    assert response.json()["feature_disabled"] == "security"
