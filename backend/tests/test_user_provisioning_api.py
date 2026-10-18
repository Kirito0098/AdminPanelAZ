"""Stage 1 Task 8: admin provisioning API.

TDD: ожидаемое FAIL до реализации маршрутов, затем PASS после Task 3.
"""

import json

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user_access_token
from app.database import Base, get_db
from app.models import Node, NodeStatus, User, UserRole, UserNodeAssignment, VpnConfig, VpnType
from app.routers import users as users_router
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
    user = User(username="admin", password_hash="x", role=UserRole.admin, is_active=True)
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
def proxy_node(db):
    node = Node(
        name="Proxy", host="127.0.0.3", port=9100, api_key_hash="h", api_key_encrypted="e",
        status=NodeStatus.online, is_local=True, node_kind="proxy", node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


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

    def fake_deprovision_config(session, *, config, actor, notify=False, **_kwargs):
        session.delete(config)
        session.commit()

    monkeypatch.setattr("app.services.user_provisioning.provision_config", fake_provision_config)
    monkeypatch.setattr("app.services.user_provisioning.deprovision_config", fake_deprovision_config)
    monkeypatch.setattr(admin_notify_service, "send", lambda *a, **k: None)

    app = FastAPI()
    app.include_router(users_router.router, prefix="/api")

    def _get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _headers(db, admin):
    return {"Authorization": f"Bearer {create_user_access_token(admin)}"}


def _provisioned_payload(node_ids, **overrides):
    payload = {
        "username": "ivan",
        "client_base_name": "ivan",
        "node_ids": list(node_ids),
        "protocols": ["wireguard"],
        "config_count": 1,
        "panel_login_enabled": False,
    }
    payload.update(overrides)
    return payload


def _user_row(db, username):
    return db.query(User).filter(User.username == username).one()


# 1. POST /users/provisioned -> 202, task, assignment rows, indexes [1]
def test_post_provisioned_returns_202_and_task(client, db, admin, nodes):
    response = client.post(
        "/api/users/provisioned", json=_provisioned_payload([n.id for n in nodes]), headers=_headers(db, admin)
    )
    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    body = response.json()
    assert "task_id" in body and body["task_id"]
    user_body = body["user"]
    assert user_body["role"] == "user"
    assert user_body["panel_login_enabled"] is False
    assert user_body["client_base_name"] == "ivan"
    assert user_body["provision_state"] != "unmanaged"

    ivan = _user_row(db, "ivan")
    assert ivan.role == UserRole.user
    assert ivan.client_base_name == "ivan"
    assert json.loads(ivan.plan_config_indexes) == [1]
    assignments = {row.node_id for row in db.query(UserNodeAssignment).filter_by(user_id=ivan.id).all()}
    assert assignments == {nodes[0].id, nodes[1].id}


# 2. PUT .../provisioning: delete без confirm -> 409 confirm_deletions; с флагом -> 200/202 + task
def test_put_provisioning_confirm_deletions(client, db, admin, nodes):
    ivan = User(
        username="ivan", password_hash="x", role=UserRole.user, client_base_name="ivan",
        plan_config_indexes=json.dumps([1, 2]), desired_protocols=json.dumps(["wireguard"]),
        panel_login_enabled=False,
    )
    db.add(ivan)
    db.commit()
    db.refresh(ivan)
    db.add(UserNodeAssignment(user_id=ivan.id, node_id=nodes[0].id))
    db.add(VpnConfig(node_id=nodes[0].id, client_name="ivan-2", vpn_type=VpnType.wireguard, owner_id=ivan.id))
    db.commit()

    def put(indexes, confirm):
        return client.put(
            f"/api/users/{ivan.id}/provisioning",
            json={
                "node_ids": [nodes[0].id],
                "protocols": ["wireguard"],
                "plan_config_indexes": indexes,
                "confirm_deletions": confirm,
            },
            headers=_headers(db, admin),
        )

    response = put([1], False)
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()["detail"]["code"] == "confirm_deletions"

    response = put([1], True)
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED), response.text
    assert "task_id" in response.json()
    assert json.loads(db.query(User).filter_by(id=ivan.id).one().plan_config_indexes) == [1]


# 3. DELETE последнего имени -> 409 last_config_name
def test_delete_last_config_name_409(client, db, admin, nodes):
    ivan = User(
        username="ivan", password_hash="x", role=UserRole.user, client_base_name="ivan",
        plan_config_indexes=json.dumps([1]), desired_protocols=json.dumps(["wireguard"]),
        panel_login_enabled=False,
    )
    db.add(ivan)
    db.commit()
    db.refresh(ivan)
    db.add(UserNodeAssignment(user_id=ivan.id, node_id=nodes[0].id))
    db.commit()

    response = client.delete(
        f"/api/users/{ivan.id}/provisioning/configs/1", headers=_headers(db, admin)
    )
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()["detail"]["code"] == "last_config_name"


# 4. POST .../configs -> самый свободный индекс (2 при [1,3])
def test_post_provisioning_configs_adds_lowest_free_index(client, db, admin, nodes):
    ivan = User(
        username="ivan", password_hash="x", role=UserRole.user, client_base_name="ivan",
        plan_config_indexes=json.dumps([1, 3]), desired_protocols=json.dumps(["wireguard"]),
        panel_login_enabled=False,
    )
    db.add(ivan)
    db.commit()
    db.refresh(ivan)
    db.add(UserNodeAssignment(user_id=ivan.id, node_id=nodes[0].id))
    db.commit()

    response = client.post(
        f"/api/users/{ivan.id}/provisioning/configs", json={}, headers=_headers(db, admin)
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    ivan = db.query(User).filter_by(id=ivan.id).one()
    assert json.loads(ivan.plan_config_indexes) == [1, 2, 3]


# 5. GET .../provisioning для пользователя без плана: префилл base/indexes/ноды/протоколы
def test_get_provisioning_unmanaged_prefill(client, db, admin, nodes):
    ivan = User(username="ivan", password_hash="x", role=UserRole.user, panel_login_enabled=False)
    db.add(ivan)
    db.commit()
    db.refresh(ivan)
    db.add_all(
        [UserNodeAssignment(user_id=ivan.id, node_id=node.id) for node in nodes]
    )
    db.add_all(
        [
            VpnConfig(node_id=nodes[0].id, client_name="ivan", vpn_type=VpnType.wireguard, owner_id=ivan.id),
            VpnConfig(node_id=nodes[1].id, client_name="ivan-3", vpn_type=VpnType.wireguard, owner_id=ivan.id),
        ]
    )
    db.commit()

    response = client.get(f"/api/users/{ivan.id}/provisioning", headers=_headers(db, admin))
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["has_plan"] is False
    suggested = body["suggested"]
    assert suggested["client_base_name"] == "ivan"
    assert suggested["plan_config_indexes"] == [1, 3]
    assert set(suggested["node_ids"]) == {nodes[0].id, nodes[1].id}
    assert "wireguard" in suggested["protocols"]


# 6. GET /users — сводка предоставления не ломает существующие поля
def test_list_users_includes_provision_summary(client, db, admin, nodes):
    ivan = User(
        username="ivan", password_hash="x", role=UserRole.user, client_base_name="ivan",
        plan_config_indexes=json.dumps([1]), desired_protocols=json.dumps(["wireguard"]),
        panel_login_enabled=False, provision_state="pending",
    )
    db.add(ivan)
    db.commit()

    response = client.get("/api/users", headers=_headers(db, admin))
    assert response.status_code == status.HTTP_200_OK, response.text
    users = response.json()
    ivan_row = next(row for row in users if row["username"] == "ivan")
    assert ivan_row["provision_state"] == "pending"
    assert ivan_row["panel_login_enabled"] is False
    assert ivan_row["role"] == "user"


# 7. Прокси-узел нельзя назначать в план
def test_reject_proxy_node_assignment(client, db, admin, nodes, proxy_node):
    response = client.post(
        "/api/users/provisioned",
        json=_provisioned_payload([nodes[0].id, proxy_node.id], username="petr"),
        headers=_headers(db, admin),
    )
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY), response.text
    detail = response.json().get("detail", "")
    assert "прокси" in str(detail).lower(), detail
