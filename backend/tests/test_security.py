"""Security hardening tests."""

from unittest.mock import patch

import pyotp
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import create_2fa_pending_token, decode_2fa_pending_token
from app.config import Settings
from app.models import User, UserRole
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
    from app.database import SessionLocal
    from app.main import app

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        assert user is not None
        raw, _ = create_refresh_token(db, user)
    finally:
        db.close()

    client = TestClient(app)
    response = client.post("/api/auth/refresh", cookies={"refresh_token": raw})
    assert response.status_code == 200
    assert "access_token" in response.json()


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
