"""Скачивание профиля: владелец-неадмин — 200, чужой конфиг — 404, админ — 200.

Регрессия: ``GET /api/users/{user_id}/configs/{config_id}/download`` требовал
админа, хотя карточки профилей приходят обычному пользователю из
``/api/configs/profile-files`` (owner ∪ грант).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.database import Base, get_db
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.routers import users as users_router

ADMIN_ID, OWNER_ID, OTHER_ID = 1, 2, 3
PROFILE_PATH = "openvpn/alice.ovpn"
PROFILE_BODY = "client\ndev tun\nproto udp\nremote vpn.example.com 1194\n"


class _FakeAdapter:
    """Подменяет файловый слой узла: контент не берём из прод-каталогов."""

    def get_profile_files(self, client_name: str, vpn_type: VpnType) -> list[dict[str, str]]:
        return [
            {
                "path": PROFILE_PATH,
                "protocol": "openvpn",
                "variant": "vpn",
                "kind": "config",
            }
        ]

    def read_profile_file(self, path: str) -> str:
        return PROFILE_BODY


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def config_id(db, monkeypatch):
    db.add_all(
        [
            User(id=ADMIN_ID, username="admin", password_hash="x", role=UserRole.admin, is_active=True),
            User(id=OWNER_ID, username="owner", password_hash="x", role=UserRole.user, is_active=True),
            User(id=OTHER_ID, username="other", password_hash="x", role=UserRole.user, is_active=True),
            Node(id=1, name="local", host="127.0.0.1", is_local=True, status=NodeStatus.online),
        ]
    )
    config = VpnConfig(node_id=1, client_name="alice", vpn_type=VpnType.openvpn, owner_id=OWNER_ID)
    db.add(config)
    db.commit()
    db.refresh(config)
    monkeypatch.setattr(users_router, "get_adapter_for_node", lambda _node: _FakeAdapter())
    monkeypatch.setattr(users_router, "load_node_remote_hosts", lambda _db, _node_id: [])
    return config.id


def _client(db, user_id: int) -> TestClient:
    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, user_id)
    return TestClient(app)


def _download(client: TestClient, user_id: int, config_id: int):
    return client.get(
        f"/api/users/{user_id}/configs/{config_id}/download",
        params={"path": PROFILE_PATH},
    )


def test_owner_downloads_own_profile(db, config_id):
    response = _download(_client(db, OWNER_ID), OWNER_ID, config_id)

    assert response.status_code == 200
    assert response.text == PROFILE_BODY
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "alice.ovpn" in disposition


def test_non_admin_cannot_download_foreign_profile(db, config_id):
    # OWNER_ID в URL — попытка подставить чужой owner_id; решает current_user.
    response = _download(_client(db, OTHER_ID), OWNER_ID, config_id)

    assert response.status_code == 404
    assert response.json()["detail"] == "Конфигурация не найдена"
    assert PROFILE_BODY not in response.text


def test_admin_downloads_any_profile(db, config_id):
    response = _download(_client(db, ADMIN_ID), OWNER_ID, config_id)

    assert response.status_code == 200
    assert response.text == PROFILE_BODY
