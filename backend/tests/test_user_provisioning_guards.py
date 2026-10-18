"""Stage 1 Task 10: in-plan guards on ``/configs`` + plan-aware self-service quota (D3).

Ожидаемое FAIL до реализации Task 3, PASS после.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token
from app.database import Base, get_db
from app.models import Node, NodeStatus, User, UserRole, UserNodeAssignment, VpnConfig, VpnType
from app.routers import configs as configs_router
from app.services.admin_notify import admin_notify_service
from app.services.self_service import build_quota_payload, enforce_user_can_create_config


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def admin(db):
    user = User(
        username="admin", password_hash="x", role=UserRole.admin, is_active=True,
        panel_login_enabled=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def nodes(db):
    first = Node(
        name="Germany", host="127.0.0.1", port=9100, api_key_hash="h", api_key_encrypted="e",
        status=NodeStatus.online, is_local=True, node_kind="vpn", node_metadata="{}",
    )
    second = Node(
        name="USA", host="127.0.0.2", port=9100, api_key_hash="h", api_key_encrypted="e",
        status=NodeStatus.online, is_local=True, node_kind="vpn", node_metadata="{}",
    )
    db.add_all([first, second])
    db.commit()
    db.refresh(first)
    db.refresh(second)
    return first, second


@pytest.fixture()
def client(db, monkeypatch, nodes):
    TestSessionLocal = sessionmaker(bind=db.bind)
    monkeypatch.setattr("app.services.background_tasks.SessionLocal", lambda: TestSessionLocal())
    monkeypatch.setattr("app.services.user_provisioning.SessionLocal", lambda: TestSessionLocal())

    def sync_submit(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("app.services.user_provisioning._submit_in_current_context", sync_submit)

    class Features:
        def is_enabled(self, key):
            return True

    monkeypatch.setattr("app.services.user_provisioning.get_feature_service", lambda: Features())
    monkeypatch.setattr("app.routers.configs.get_feature_service", lambda: Features())

    def fake_provision_config(session, *, node, client_name, vpn_type, owner, actor, notify=False, **_kwargs):
        existing = (
            session.query(VpnConfig)
            .filter_by(node_id=node.id, client_name=client_name, vpn_type=vpn_type)
            .first()
        )
        if existing is not None:
            return (existing, None)
        config = VpnConfig(node_id=node.id, client_name=client_name, vpn_type=vpn_type, owner_id=owner.id)
        session.add(config)
        session.commit()
        session.refresh(config)
        return (config, None)

    def fake_deprovision_config(session, *, config, actor, notify=False, request=None, **_kwargs):
        session.delete(config)
        session.commit()

    monkeypatch.setattr("app.routers.configs.provision_config", fake_provision_config)
    monkeypatch.setattr("app.routers.configs.deprovision_config", fake_deprovision_config)
    monkeypatch.setattr(admin_notify_service, "send", lambda *a, **k: None)
    monkeypatch.setattr(admin_notify_service, "send_config_delete", lambda *a, **k: None)

    class FakeAdapter:
        def get_profile_files(self, client_name, vpn_type):
            return []

    monkeypatch.setattr("app.routers.configs.get_active_adapter", lambda db: FakeAdapter())

    from app.services.node_manager import set_active_node_id

    set_active_node_id(db, nodes[0].id)

    app = FastAPI()
    app.include_router(configs_router.router, prefix="/api")

    def _get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _headers(db, user):
    return {"Authorization": f"Bearer {create_user_access_token(user)}"}


def _planned_user(db, username="ivan", base="ivan", indexes=None, node=None, can_manage=False,
                  protocols=None):
    indexes = indexes or [1]
    user = User(
        username=username,
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        panel_login_enabled=True,
        client_base_name=base,
        plan_config_indexes=json.dumps(indexes),
        desired_protocols=json.dumps(protocols or ["wireguard", "openvpn"]),
        can_manage_configs=can_manage,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if node is not None:
        db.add(UserNodeAssignment(user_id=user.id, node_id=node.id))
        db.commit()
    return user


def _config(db, user, node, client_name, vpn_type=VpnType.wireguard):
    config = VpnConfig(node_id=node.id, client_name=client_name, vpn_type=vpn_type, owner_id=user.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


class _FakeDb:
    def __init__(self, setting_value: str | None = None):
        self.setting_value = setting_value

    def query(self, *models):
        name = getattr(models[0], "__name__", str(models[0])) if models else ""
        if "AppSetting" in name:
            return _FakeSettingQuery(self.setting_value)
        return _FakeVpnCountQuery(0)

    def add(self, _obj):
        return None

    def commit(self):
        return None


class _FakeSettingQuery:
    def __init__(self, value: str | None):
        self._value = value

    def filter(self, *_a, **_k):
        return self

    def first(self):
        if self._value is None:
            return None
        return SimpleNamespace(value=self._value)


class _FakeVpnCountQuery:
    def __init__(self, count: int):
        self._count = count

    def filter(self, *_a, **_k):
        return self

    def distinct(self):
        return self

    def all(self):
        return []


# --- Task 2 cases ---

def test_planned_user_cannot_post_configs(client, db, admin, nodes):
    ivan = _planned_user(db, node=nodes[0])
    response = client.post(
        "/api/configs",
        json={"client_name": "ivan-9", "vpn_type": "wireguard"},
        headers=_headers(db, ivan),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
    assert "Мои конфиги" in response.json()["detail"], response.text


def test_non_admin_in_plan_delete_403(client, db, nodes):
    ivan = _planned_user(db, node=nodes[0])
    config = _config(db, ivan, nodes[0], "ivan")
    response = client.delete(f"/api/configs/{config.id}", headers=_headers(db, ivan))
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
    assert "Мои конфиги" in response.json()["detail"], response.text


def test_non_admin_in_plan_cert_patch_403(client, db, nodes):
    ivan = _planned_user(db, node=nodes[0])
    config = _config(db, ivan, nodes[0], "ivan", VpnType.openvpn)
    response = client.patch(
        f"/api/configs/{config.id}",
        json={"cert_expire_days": 3000},
        headers=_headers(db, ivan),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
    assert "Мои конфиги" in response.json()["detail"], response.text


def test_off_plan_delete_follows_can_manage(client, db, nodes):
    ivan = _planned_user(db, node=nodes[0])
    config = _config(db, ivan, nodes[0], "extra-client")  # не под base → off-plan

    response = client.delete(f"/api/configs/{config.id}", headers=_headers(db, ivan))
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
    assert "Мои конфиги" not in response.json()["detail"]

    ivan.can_manage_configs = True
    db.commit()

    response = client.delete(f"/api/configs/{config.id}", headers=_headers(db, ivan))
    assert response.status_code == status.HTTP_200_OK, response.text
    assert db.get(VpnConfig, config.id) is None


def test_global_quota_counts_names_not_files():
    user = SimpleNamespace(
        id=7,
        role=UserRole.user,
        client_base_name="ivan",
        plan_config_indexes=json.dumps([1, 2]),
        config_quota=2,
    )
    db = _FakeDb(setting_value="2")
    payload = build_quota_payload(db, user)
    assert payload["used"] == 2
    assert payload["limit"] == 2
    assert payload["remaining"] == 0
    assert payload["can_create"] is False

    with pytest.raises(HTTPException) as exc:
        enforce_user_can_create_config(db, user)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Достигнут лимит конфигураций (2)" in str(exc.value.detail)

    # рост имён плана — quota исчерпана ещё сильнее; файлы при этом не создавались
    user.plan_config_indexes = json.dumps([1, 2, 3])
    payload = build_quota_payload(db, user)
    assert payload["used"] == 3
    assert payload["can_create"] is False


def test_admin_delete_in_plan_sets_pending(client, db, admin, nodes):
    ivan = _planned_user(db, node=nodes[0])
    config = _config(db, ivan, nodes[0], "ivan")
    assert config.owner_id == ivan.id

    response = client.delete(f"/api/configs/{config.id}", headers=_headers(db, admin))
    assert response.status_code == status.HTTP_200_OK, response.text
    assert db.get(VpnConfig, config.id) is None

    ivan_row = db.query(User).filter_by(id=ivan.id).one()
    assert ivan_row.provision_state == "pending"


def test_unmanaged_user_post_configs_unchanged(client, db, nodes):
    personal = User(
        username="personal", password_hash="x", role=UserRole.user, is_active=True,
        panel_login_enabled=True,
    )
    db.add(personal)
    db.commit()
    db.refresh(personal)

    response = client.post(
        "/api/configs",
        json={"client_name": "personal", "vpn_type": "wireguard"},
        headers=_headers(db, personal),
    )
    assert "Мои конфиги" not in response.text, response.text
    assert response.status_code != status.HTTP_403_FORBIDDEN, response.text
