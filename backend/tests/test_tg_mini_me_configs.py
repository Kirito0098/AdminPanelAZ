"""Stage 1 Task 11: Mini App ``/tg-mini/me/configs`` (все узлы владельца) + самосервис ``/me/plan-configs``.

Ожидаемый FAIL до реализации Task 11, PASS после.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token, get_tg_mini_user
from app.database import Base, get_db
from app.models import Node, NodeStatus, User, UserRole, UserNodeAssignment, VpnConfig, VpnType
from app.routers.tg_mini.configs import router as mini_configs_router
from app.routers.tg_mini.me_configs import router as me_configs_router
from app.routers import me as me_router
from app.services.admin_notify import admin_notify_service


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


def _headers(db, user):
    return {"Authorization": f"Bearer {create_user_access_token(user)}"}


def _me_user(db, username="ivan", indexes=None, can_manage=False, can_create=True, telegram_id="111",
             plan=True):
    user = User(
        username=username,
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        panel_login_enabled=True,
        client_base_name=username if plan else None,
        plan_config_indexes=json.dumps(indexes or [1]) if plan else None,
        desired_protocols=json.dumps(["wireguard"]) if plan else None,
        can_manage_configs=can_manage,
        can_create_configs=can_create,
        telegram_id=telegram_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _config(db, user, node, client_name, vpn_type=VpnType.wireguard, shadow=False):
    config = VpnConfig(
        node_id=node.id,
        client_name=client_name,
        vpn_type=vpn_type,
        owner_id=user.id,
        ha_primary_config_id=999 if shadow else None,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


# --- tg-mini /me/configs client (auth через get_tg_mini_user, как у остальных tg_mini эндпоинтов) ---

@pytest.fixture()
def tg_client(db):
    def _get_db():
        try:
            yield db
        finally:
            pass

    app = FastAPI()
    app.include_router(mini_configs_router, prefix="/api/tg-mini")
    app.include_router(me_configs_router, prefix="/api/tg-mini")
    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


# --- /me/plan-configs client (обычный panel JWT + provisioning моки, как в test_user_provisioning_api) ---

@pytest.fixture()
def me_client(db, monkeypatch, nodes):
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
    monkeypatch.setattr(admin_notify_service, "send", lambda *a, **k: None)

    app = FastAPI()
    app.include_router(me_router.router, prefix="/api")

    def _get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


# --- Task 11.1: me/configs списка по всем узлам, тени скрыты ---

def test_me_configs_lists_both_nodes(tg_client, db, nodes):
    ivan = _me_user(db, telegram_id="111")
    tg_client.app.dependency_overrides[get_tg_mini_user] = lambda: ivan
    # Одно имя на двух узлах → группа содержит оба node_id.
    _config(db, ivan, nodes[0], "ivan")
    _config(db, ivan, nodes[1], "ivan")
    _config(db, ivan, nodes[1], "shadow", shadow=True)  # HA-тень — скрыть из списка

    response = tg_client.get("/api/tg-mini/me/configs")
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    names = {item["name"] for item in body["configs"]}
    assert names == {"ivan"}, body

    ivan_entry = next(item for item in body["configs"] if item["name"] == "ivan")
    assert {n["node_id"] for n in ivan_entry["nodes"]} == {nodes[0].id, nodes[1].id}, ivan_entry
    for node_entry in ivan_entry["nodes"]:
        assert set(node_entry) == {"node_id", "node_label", "vpn_type", "config_id"}, node_entry


def test_me_files_owner_mismatch_404(tg_client, db, nodes):
    ivan = _me_user(db, telegram_id="111")
    petr = _me_user(db, username="petr", telegram_id="222")
    tg_client.app.dependency_overrides[get_tg_mini_user] = lambda: petr

    config = _config(db, ivan, nodes[0], "ivan")
    response = tg_client.get(f"/api/tg-mini/me/configs/{config.id}/files")
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
    assert response.json()["detail"] == "Конфигурация не найдена", response.text
    # Чужой конфиг не тронут.
    assert db.get(VpnConfig, config.id) is not None


def test_me_files_uses_config_node(tg_client, db, nodes, monkeypatch):
    ivan = _me_user(db, telegram_id="111")
    tg_client.app.dependency_overrides[get_tg_mini_user] = lambda: ivan

    # Конфиг лежит на nodes[1]; активный узел не задан и не должен использоваться.
    config = _config(db, ivan, nodes[1], "ivan")
    calls: list[int] = []
    stub = SimpleNamespace(
        get_profile_files=lambda client_name, vpn_type: [
            {"path": "client.conf", "protocol": "wireguard", "variant": ""}
        ]
    )

    def fake_adapter(node):
        calls.append(node.id)
        return stub

    monkeypatch.setattr("app.routers.tg_mini.me_configs.get_adapter_for_node", fake_adapter)
    with patch(
        "app.routers.tg_mini.me_configs.resolve_effective_visible_vpn_profiles",
        return_value={"routes": ["vpn"], "protocols": ["wireguard"], "openvpn_groups": []},
    ):
        response = tg_client.get(f"/api/tg-mini/me/configs/{config.id}/files")

    assert response.status_code == status.HTTP_200_OK, response.text
    assert calls == [nodes[1].id], calls
    assert any(file_item["path"] == "client.conf" for file_item in response.json()["files"]), response.json()


def test_me_qr_link_route_is_under_me_prefix(tg_client, db, nodes, monkeypatch):
    """Mini App calls /me/qr-link; a bare /qr-link must not be the owner path (was 404 Not Found)."""
    ivan = _me_user(db, telegram_id="111")
    tg_client.app.dependency_overrides[get_tg_mini_user] = lambda: ivan
    config = _config(db, ivan, nodes[1], "ivan")
    stub = SimpleNamespace(
        get_profile_files=lambda client_name, vpn_type: [
            {"path": "client.conf", "protocol": "wireguard", "variant": "vpn"}
        ]
    )
    monkeypatch.setattr(
        "app.routers.tg_mini.me_configs.get_adapter_for_node",
        lambda node: stub,
    )
    monkeypatch.setattr(
        "app.routers.tg_mini.me_configs.resolve_effective_visible_vpn_profiles",
        lambda *_a, **_k: {
            "routes": ["vpn"],
            "protocols": ["wireguard"],
            "openvpn_groups": [],
            "awg2_tunnel_only": True,
        },
    )
    monkeypatch.setattr(
        "app.routers.tg_mini.me_configs._qr_download_service",
        lambda db, request: SimpleNamespace(
            create_token=lambda **kwargs: {
                "url": "https://example.test/d/token",
                "token": "t",
                "expires_at": "2099-01-01T00:00:00Z",
            }
        ),
    )

    # Owner Mini App uses /me/qr-link (frontend getTgQrLink); bare /qr-link is admin-active only.
    ok = tg_client.get(
        f"/api/tg-mini/me/qr-link?config_id={config.id}&path=client.conf"
    )
    assert ok.status_code == status.HTTP_200_OK, ok.text
    assert ok.json()["url"] == "https://example.test/d/token", ok.json()


# --- Task 11.2: самосервис /me/plan-configs (квота D3) ---

def test_plan_configs_self_service_quota(me_client, db, nodes):
    from app.services.app_setting_store import _set_setting

    ivan = _me_user(db, indexes=[1], can_manage=True, can_create=True)

    # quota=1, план уже содержит имя 1 → исчерпано → 400.
    _set_setting(db, "user_config_quota_default", "1")
    db.commit()
    response = me_client.post("/api/me/plan-configs", headers=_headers(db, ivan))
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text
    assert "Достигнут лимит конфигураций" in response.json()["detail"], response.text

    # quota=2 →最低 свободный индекс 2, задача применения.
    _set_setting(db, "user_config_quota_default", "2")
    db.commit()
    ivan = db.query(User).filter_by(id=ivan.id).one()
    ivan.plan_config_indexes = json.dumps([1])
    db.commit()

    response = me_client.post("/api/me/plan-configs", headers=_headers(db, ivan))
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED), response.text
    body = response.json()
    assert body["index"] == 2, body
    assert "task_id" in body and body["task_id"], body

    ivan = db.query(User).filter_by(id=ivan.id).one()
    assert json.loads(ivan.plan_config_indexes) == [1, 2]


# --- Task 11.3: DELETE /me/plan-configs/{index} требует can_manage ---

def test_plan_configs_delete_requires_can_manage(me_client, db):
    ivan = _me_user(db, indexes=[1, 2], can_manage=False, can_create=True)
    response = me_client.delete("/api/me/plan-configs/2", headers=_headers(db, ivan))
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text

    ivan.can_manage_configs = True
    db.commit()

    # последнее имя плана удалить нельзя → 409 last_config_name
    ivan = db.query(User).filter_by(id=ivan.id).one()
    ivan.plan_config_indexes = json.dumps([1])
    db.commit()

    response = me_client.delete("/api/me/plan-configs/1", headers=_headers(db, ivan))
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()["detail"]["code"] == "last_config_name", response.text
