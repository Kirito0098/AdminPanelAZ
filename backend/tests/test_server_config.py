"""Server config from the web: admin only, one run at a time, script output parsed."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token, get_password_hash
from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import system as system_router
from app.services import server_config

PREVIEW_TSV = (
    "add\tПакеты системы: jq\n"
    "change\tКонфиг nginx для a.example устарел — обновится\n"
    'minus\tadd_header X-Frame-Options "SAMEORIGIN" always;\n'
    "why\tЗаголовки безопасности теперь ставит сама панель\n"
    "recheck\tПравила firewall AdminPanelAZ проверятся\n"
    "keep\tСлужбы systemd — без изменений\n"
    "effect\tПанель и агенты не перезапускаются\n"
)


@pytest.fixture
def db_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all(
            [
                User(
                    username="admin",
                    password_hash=get_password_hash("x-Admin-123"),
                    role=UserRole.admin,
                    is_active=True,
                ),
                User(username="bob", password_hash=get_password_hash("x-User-123"), role=UserRole.user, is_active=True),
            ]
        )
        db.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def client(db_factory, monkeypatch):
    monkeypatch.setattr(system_router, "log_action", lambda *_a, **_k: None)
    app = FastAPI()
    app.include_router(system_router.router, prefix="/api")

    def _get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _auth(db_factory, username: str) -> dict[str, str]:
    with db_factory() as db:
        token = create_user_access_token(db.query(User).filter(User.username == username).one())
    return {"Authorization": f"Bearer {token}"}


def test_server_config_admin_only_single_run_and_parsed(client, db_factory, monkeypatch):
    monkeypatch.setattr(server_config, "_run_script", lambda *_a, **_k: PREVIEW_TSV)
    user = _auth(db_factory, "bob")
    assert client.get("/api/system/update/server-config", headers=user).status_code == 403
    assert client.post("/api/system/update/server-config", headers=user).status_code == 403

    admin = _auth(db_factory, "admin")
    body = client.get("/api/system/update/server-config", headers=admin).json()
    assert body["pending"] == 2
    assert body["details"] == {
        "Конфиг nginx для a.example устарел — обновится": {
            "removed": ['add_header X-Frame-Options "SAMEORIGIN" always;'],
            "added": [],
            "why": ["Заголовки безопасности теперь ставит сама панель"],
            "info": [],
        }
    }
    assert body["sections"]["add"] == ["Пакеты системы: jq"]
    assert body["sections"]["recheck"] == ["Правила firewall AdminPanelAZ проверятся"]

    monkeypatch.setattr(
        system_router.background_task_service,
        "find_active_task",
        lambda task_type: SimpleNamespace(id="t1") if task_type == "update_system" else None,
    )
    assert client.post("/api/system/update/server-config", headers=admin).status_code == 409

    assert server_config.parse_report("apt\tok\tдоустановлено: 0\nnginx\tошибка\tnginx -t\n") == {
        "success": False,
        "message": "Есть ошибки: 1",
        "rows": [
            {"step": "apt", "label": "Пакеты", "status": "ok", "detail": "доустановлено: 0"},
            {"step": "nginx", "label": "nginx", "status": "ошибка", "detail": "nginx -t"},
        ],
    }


@pytest.mark.parametrize("path", ["/api/system/update", "/api/system/rebuild"])
def test_update_and_rebuild_wait_for_server_config(client, db_factory, monkeypatch, path):
    monkeypatch.setattr(system_router, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda _key: True))
    monkeypatch.setattr(
        system_router.background_task_service,
        "find_active_task",
        lambda task_type: SimpleNamespace(id="t1") if task_type == "server_config" else None,
    )
    monkeypatch.setattr(
        system_router.background_task_service,
        "enqueue_background_task",
        lambda *_a, **_k: pytest.fail("started while server config is being applied"),
    )

    assert client.post(path, headers=_auth(db_factory, "admin")).status_code == 409
