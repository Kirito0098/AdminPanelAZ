"""Admin bootstrap: DB as password source of truth, .env scrub after change."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, get_password_hash, verify_password
from app.config import Settings
from app.database import Base
from app.models import User, UserRole
from app.services.admin_bootstrap import (
    scrub_admin_bootstrap_secret_from_env,
    upsert_bootstrap_admin,
)
from app.services.env_file import EnvFileService


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_upsert_bootstrap_admin_create_only_when_missing(db_session, monkeypatch):
    monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "bootstrap_admin")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "BootstrapP@ss1")
    settings = Settings()

    assert upsert_bootstrap_admin(db_session, force=False, settings=settings) == "created"
    user = db_session.query(User).filter(User.username == "bootstrap_admin").first()
    assert user is not None
    assert verify_password("BootstrapP@ss1", user.password_hash)

    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "OtherP@ss2")
    settings2 = Settings()
    assert upsert_bootstrap_admin(db_session, force=False, settings=settings2) == "skipped"
    db_session.refresh(user)
    assert verify_password("BootstrapP@ss1", user.password_hash)
    assert not verify_password("OtherP@ss2", user.password_hash)


def test_upsert_bootstrap_admin_force_updates(db_session, monkeypatch):
    monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "force_admin")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "FirstP@ss1")
    settings = Settings()
    upsert_bootstrap_admin(db_session, force=True, settings=settings)

    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "SecondP@ss2")
    settings2 = Settings()
    assert upsert_bootstrap_admin(db_session, force=True, settings=settings2) == "updated"
    user = db_session.query(User).filter(User.username == "force_admin").first()
    assert verify_password("SecondP@ss2", user.password_hash)


def test_scrub_admin_bootstrap_secret_from_env(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_ADMIN_PASSWORD=secret123\nOTHER=value\n", encoding="utf-8")
    settings = Settings(default_admin_password="secret123")

    assert scrub_admin_bootstrap_secret_from_env(env_path=env_file, settings=settings) is True
    content = env_file.read_text(encoding="utf-8")
    assert "DEFAULT_ADMIN_PASSWORD=\n" in content or content.endswith("DEFAULT_ADMIN_PASSWORD=")
    assert "secret123" not in content

    assert scrub_admin_bootstrap_secret_from_env(env_path=env_file, settings=settings) is False


def test_change_password_scrubs_env(db_session, monkeypatch, tmp_path):
    from app.database import get_db
    from app.main import app

    env_file = tmp_path / ".env"
    env_file.write_text("DEFAULT_ADMIN_PASSWORD=OldBootstrap1\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.admin_bootstrap.resolve_backend_env_path",
        lambda: env_file,
    )
    monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "OldBootstrap1")

    test_settings = Settings(
        app_env="development",
        enforce_password_policy=False,
        default_admin_username="admin",
        default_admin_password="OldBootstrap1",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: test_settings)
    monkeypatch.setattr("app.routers.auth.settings", test_settings)

    user = User(
        username="admin",
        password_hash=get_password_hash("CurrentP@ss1"),
        role=UserRole.admin,
        theme="dark",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        "app.services.ip_restriction.ip_restriction_service.login_needs_captcha",
        lambda _ip: False,
    )
    monkeypatch.setattr(
        "app.services.ip_restriction.ip_restriction_service.get_client_ip",
        lambda _req: "127.0.0.1",
    )
    monkeypatch.setattr("app.services.auth_rate_limit.auth_rate_limit_service.check", lambda _ip: None)

    token = create_access_token({"sub": "admin", "role": UserRole.admin.value})
    client = TestClient(app)
    try:
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": "CurrentP@ss1", "new_password": "NewSecureP@ss2"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert EnvFileService(env_file).get_env_value("DEFAULT_ADMIN_PASSWORD", "x") == ""
    finally:
        app.dependency_overrides.clear()
