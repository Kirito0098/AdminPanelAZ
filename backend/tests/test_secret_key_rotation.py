"""Ротация SECRET_KEY: все секреты в БД перешифровываются, все сессии завершаются."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database import Base
from app.models import Node, RefreshToken, User, UserRole
from app.services import secrets_rotation as sr
from app.services.crypto import decrypt_secret, encrypt_secret

OLD_KEY = "old-secret-key-0123456789-abcdefghij"
NEW_KEY = "new-secret-key-0123456789-abcdefghij"


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def rotate(db, tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(f"SECRET_KEY={OLD_KEY}\n")
    monkeypatch.setattr(sr, "_panel_env_path", lambda: env_path)
    monkeypatch.setenv("SECRET_KEY", OLD_KEY)
    get_settings.cache_clear()

    def _run():
        token = sr._create_preview_token("secret_key", sr._hash_value(NEW_KEY), OLD_KEY)
        return sr.SecretsRotationService().apply(
            db,
            "secret_key",
            new_value=NEW_KEY,
            preview_token=token,
            confirm=sr.CONFIRM_PHRASE,
            old_settings=SimpleNamespace(secret_key=OLD_KEY, is_production=False),
        )

    yield _run
    get_settings.cache_clear()


def _ssh_node(db) -> Node:
    node = Node(
        name="ssh-node",
        host="203.0.113.5",
        api_key_hash="h",
        api_key_encrypted=encrypt_secret("agent-key", OLD_KEY),
        ssh_private_key_encrypted=encrypt_secret("-----BEGIN OPENSSH PRIVATE KEY-----", OLD_KEY),
        ssh_passphrase_encrypted=encrypt_secret("phrase", OLD_KEY),
    )
    db.add(node)
    db.commit()
    return node


def test_rotation_reencrypts_ssh_transport_credentials(db, rotate):
    node = _ssh_node(db)

    rotate()

    db.refresh(node)
    assert decrypt_secret(node.api_key_encrypted, NEW_KEY) == "agent-key"
    assert decrypt_secret(node.ssh_private_key_encrypted, NEW_KEY) == "-----BEGIN OPENSSH PRIVATE KEY-----"
    assert decrypt_secret(node.ssh_passphrase_encrypted, NEW_KEY) == "phrase"


def test_rotation_keeps_empty_ssh_fields_empty(db, rotate):
    node = Node(name="plain", host="203.0.113.6", api_key_hash="h", api_key_encrypted=encrypt_secret("k", OLD_KEY))
    db.add(node)
    db.commit()

    result = rotate()

    db.refresh(node)
    assert node.ssh_private_key_encrypted == ""
    assert node.ssh_passphrase_encrypted == ""
    assert result["reencrypt_stats"]["errors"] == 0


def test_rotation_ends_every_session(db, rotate):
    users = [
        User(username="admin", password_hash="x", role=UserRole.admin, is_active=True, token_version=3),
        User(username="bob", password_hash="x", role=UserRole.user, is_active=True),
    ]
    db.add_all(users)
    db.commit()
    for user in users:
        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=f"hash-{user.username}",
                family_id=f"fam-{user.username}",
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
        )
    db.commit()

    rotate()

    assert db.query(RefreshToken).filter(RefreshToken.revoked.is_(False)).count() == 0
    db.expire_all()
    versions = {u.username: u.token_version for u in db.query(User).all()}
    assert versions == {"admin": 4, "bob": 1}


def test_rotation_names_the_real_panel_unit(rotate):
    result = rotate()

    assert "Перезапустите панель (sudo systemctl restart adminpanelaz)." in result["next_steps"]
