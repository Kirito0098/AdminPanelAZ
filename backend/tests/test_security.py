"""Security hardening tests."""

from unittest.mock import MagicMock, patch

import pyotp
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import create_2fa_pending_token, decode_2fa_pending_token
from app.config import Settings
from app.models import User, UserRole, ViewerConfigAccess, VpnConfig
from app.services.auth_rate_limit import AuthRateLimitService, MemoryRateLimitBackend
from app.services.password_policy import effective_min_password_length, validate_password
from app.services.refresh_token import create_refresh_token, revoke_refresh_token, validate_refresh_token
from app.services.security_bootstrap import validate_node_agent_key, validate_panel_settings
from app.services.totp_service import encrypt_totp_secret, generate_totp_secret, verify_totp_code


def test_password_policy_dev_allows_short_password():
    settings = Settings(app_env="development", enforce_password_policy=False)
    assert effective_min_password_length(settings) == 4
    validate_password("abcd", settings=settings)


def test_password_policy_production_requires_complexity():
    settings = Settings(app_env="production", min_password_length=8)
    with pytest.raises(HTTPException) as exc:
        validate_password("short", settings=settings)
    assert "8" in str(exc.value.detail)

    with pytest.raises(HTTPException) as exc:
        validate_password("allletters", username="user1", settings=settings)
    assert "цифры" in str(exc.value.detail)

    validate_password("SecurePass1", username="user1", settings=settings)


def test_production_secret_validation_rejects_defaults():
    settings = Settings(app_env="production", secret_key="change-me-in-production-use-long-random-string")
    with pytest.raises(SystemExit):
        validate_panel_settings(settings)


def test_production_secret_validation_accepts_strong_key():
    settings = Settings(
        app_env="production",
        secret_key="a" * 32,
        default_admin_password="Str0ngP@ss!",
    )
    validate_panel_settings(settings)


def test_node_agent_key_validation_in_production():
    with pytest.raises(SystemExit):
        validate_node_agent_key("change-me-node-agent-key", production=True)
    validate_node_agent_key("x" * 32, production=True)


def test_auth_rate_limit_blocks_after_threshold():
    service = AuthRateLimitService()
    service._backend = MemoryRateLimitBackend()
    settings = Settings(auth_rate_limit_enabled=True, auth_rate_limit_max_attempts=3, auth_rate_limit_window_seconds=60)
    with patch("app.services.auth_rate_limit.get_settings", return_value=settings):
        service.check("10.0.0.1")
        service.record_failure("10.0.0.1")
        service.record_failure("10.0.0.1")
        service.record_failure("10.0.0.1")
        with pytest.raises(HTTPException) as exc:
            service.check("10.0.0.1")
        assert exc.value.status_code == 429


def test_security_headers_middleware():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_cors_allows_configured_origin():
    from app.main import app

    client = TestClient(app)
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert "http://localhost:5173" in (response.headers.get("access-control-allow-origin") or "")


def test_refresh_token_flow():
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
            user = User(
                username="test_refresh_user",
                password_hash="x",
                role=UserRole.admin,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        raw, _ = create_refresh_token(db, user)
        validated = validate_refresh_token(db, raw)
        assert validated.id == user.id
        revoke_refresh_token(db, raw)
        with pytest.raises(HTTPException):
            validate_refresh_token(db, raw)
    finally:
        db.close()


def test_2fa_pending_token_roundtrip():
    token = create_2fa_pending_token("admin")
    assert decode_2fa_pending_token(token) == "admin"


def test_totp_verify_valid_code():
    secret = generate_totp_secret()
    user = User(username="admin", password_hash="x", role=UserRole.admin, totp_secret_encrypted=encrypt_totp_secret(secret))
    code = pyotp.TOTP(secret).now()
    assert verify_totp_code(user, code) is True


def test_auth_refresh_endpoint():
    from app.database import SessionLocal, run_db_migrations
    from app.main import app
    from app.models import ActiveWebSession

    run_db_migrations()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None
        raw, _ = create_refresh_token(db, user)
        before_count = db.query(ActiveWebSession).count()
    finally:
        db.close()

    client = TestClient(app)
    response = client.post(
        "/api/auth/refresh",
        cookies={"refresh_token": raw},
        headers={"X-Web-Session-Id": "refresh-should-not-touch"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "web_session_id" not in response.json()

    db = SessionLocal()
    try:
        assert db.query(ActiveWebSession).count() == before_count
    finally:
        db.close()


def test_login_json_returns_web_session_id():
    from app.auth import get_password_hash
    from app.database import SessionLocal, run_db_migrations
    from app.main import app

    run_db_migrations()
    test_password = "LoginSessionPass1"
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None
        user.password_hash = get_password_hash(test_password)
        user.totp_enabled = False
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    response = client.post(
        "/api/auth/login/json",
        json={"username": "admin", "password": test_password},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("access_token")
    assert data.get("web_session_id")


def test_login_requires_2fa_for_admin_with_totp():
    from app.auth import get_password_hash
    from app.database import SessionLocal
    from app.main import app

    test_password = "Test2FAPass1"
    secret = generate_totp_secret()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None
        user.password_hash = get_password_hash(test_password)
        user.totp_enabled = True
        user.totp_secret_encrypted = encrypt_totp_secret(secret)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    response = client.post(
        "/api/auth/login/json",
        json={"username": "admin", "password": test_password},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("requires_2fa") is True
    assert data.get("temp_token")

    code = pyotp.TOTP(secret).now()
    response2 = client.post(
        "/api/auth/login/2fa",
        json={"temp_token": data["temp_token"], "code": code},
    )
    assert response2.status_code == 200
    assert response2.json().get("access_token")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        user.totp_enabled = False
        user.totp_secret_encrypted = None
        user.totp_backup_codes_encrypted = None
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def viewer_config_client(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.auth import get_password_hash
    from app.database import Base, get_db
    from app.main import app
    from app.models import Node, NodeStatus, User, UserRole, ViewerConfigAccess, VpnConfig, VpnType

    db_path = tmp_path / "viewer_config.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    admin = User(
        username="vc_admin",
        password_hash=get_password_hash("secret123"),
        role=UserRole.admin,
        is_active=True,
    )
    viewer = User(
        username="vc_viewer",
        password_hash=get_password_hash("secret123"),
        role=UserRole.viewer,
        is_active=True,
    )
    regular = User(
        username="vc_user",
        password_hash=get_password_hash("secret123"),
        role=UserRole.user,
        is_active=True,
    )
    node = Node(
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    session.add_all([admin, viewer, regular, node])
    session.flush()

    session.add_all(
        [
            VpnConfig(node_id=node.id, client_name="alice", vpn_type=VpnType.openvpn, owner_id=admin.id),
            VpnConfig(node_id=node.id, client_name="alice", vpn_type=VpnType.wireguard, owner_id=admin.id),
            VpnConfig(node_id=node.id, client_name="bob", vpn_type=VpnType.openvpn, owner_id=admin.id),
            VpnConfig(node_id=node.id, client_name="charlie", vpn_type=VpnType.wireguard, owner_id=admin.id),
            ViewerConfigAccess(user_id=viewer.id, config_group="alice"),
        ]
    )
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
    mock_adapter.get_profile_files.return_value = []

    with (
        patch("app.config.get_settings", return_value=test_settings),
        patch("app.routers.configs.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.configs.get_active_node", return_value=node),
        patch("app.services.auth_rate_limit.get_settings", return_value=test_settings),
        patch("app.services.ip_restriction.ip_restriction_service.login_needs_captcha", return_value=False),
        patch("app.services.ip_restriction.ip_restriction_service.record_login_attempt", return_value=0),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.check", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_failure", return_value=None),
        patch("app.services.auth_rate_limit.auth_rate_limit_service.record_success", return_value=None),
    ):
        client = TestClient(app)

        def _login(username: str) -> dict[str, str]:
            response = client.post("/api/auth/login/json", json={"username": username, "password": "secret123"})
            assert response.status_code == 200
            token = response.json()["access_token"]
            return {"Authorization": f"Bearer {token}"}

        yield {
            "client": client,
            "admin_headers": _login("vc_admin"),
            "viewer_headers": _login("vc_viewer"),
            "user_headers": _login("vc_user"),
            "session": TestingSession,
            "viewer_id": viewer.id,
            "node": node,
        }

    app.dependency_overrides.clear()
    session.close()


def test_viewer_sees_only_granted_configs(viewer_config_client):
    client = viewer_config_client["client"]
    response = client.get("/api/configs", headers=viewer_config_client["viewer_headers"])
    assert response.status_code == 200
    names = {item["client_name"] for item in response.json()}
    assert names == {"alice"}


def test_viewer_denied_ungranted_config_detail(viewer_config_client):
    client = viewer_config_client["client"]
    db = viewer_config_client["session"]()
    try:
        bob = db.query(VpnConfig).filter(VpnConfig.client_name == "bob").first()
        assert bob is not None
        response = client.get(f"/api/configs/{bob.id}", headers=viewer_config_client["viewer_headers"])
        assert response.status_code == 403
    finally:
        db.close()


def test_viewer_without_grants_sees_empty_list(viewer_config_client):
    client = viewer_config_client["client"]
    db = viewer_config_client["session"]()
    try:
        db.query(ViewerConfigAccess).delete()
        db.commit()
    finally:
        db.close()

    response = client.get("/api/configs", headers=viewer_config_client["viewer_headers"])
    assert response.status_code == 200
    assert response.json() == []


def test_admin_can_set_viewer_access(viewer_config_client):
    client = viewer_config_client["client"]
    viewer_id = viewer_config_client["viewer_id"]

    response = client.put(
        "/api/system/viewer-access",
        headers=viewer_config_client["admin_headers"],
        json={"user_id": viewer_id, "config_groups": ["bob", "charlie"]},
    )
    assert response.status_code == 200

    get_response = client.get(f"/api/system/viewer-access/{viewer_id}", headers=viewer_config_client["admin_headers"])
    assert get_response.status_code == 200
    assert set(get_response.json()["config_groups"]) == {"bob", "charlie"}

    list_response = client.get("/api/configs", headers=viewer_config_client["viewer_headers"])
    names = {item["client_name"] for item in list_response.json()}
    assert names == {"bob", "charlie"}


def test_viewer_access_endpoints_require_admin(viewer_config_client):
    client = viewer_config_client["client"]
    viewer_id = viewer_config_client["viewer_id"]

    get_response = client.get(f"/api/system/viewer-access/{viewer_id}", headers=viewer_config_client["viewer_headers"])
    assert get_response.status_code == 403

    put_response = client.put(
        "/api/system/viewer-access",
        headers=viewer_config_client["user_headers"],
        json={"user_id": viewer_id, "config_groups": ["alice"]},
    )
    assert put_response.status_code == 403
