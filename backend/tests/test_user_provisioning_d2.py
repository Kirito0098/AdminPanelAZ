"""Stage 1 Task 9: D2 config ops, user stats, safe delete, admin telegram-link-code.

Ожидаемый FAIL до реализации Task 3, затем PASS.
"""

import json

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.models import BackgroundTask, Node, User, UserRole, UserNodeAssignment, VpnConfig, VpnType
from app.services.background_tasks import background_task_service

# Переиспользуем фикстуры db / admin / nodes / client из Task 8.
from tests.test_user_provisioning_api import client, db, admin, nodes  # noqa: F401


class _StubAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def get_profile_files(self, client_name, vpn_type):
        self.calls.append(("get_profile_files", client_name, str(vpn_type)))
        return [
            {"path": "client.ovpn", "protocol": "openvpn", "variant": ""},
            {"path": "client.conf", "protocol": "openvpn", "variant": "tcp"},
        ]

    def read_profile_file(self, path):
        self.calls.append(("read_profile_file", path))
        return "-----BEGIN OPENVPN CONFIG-----"


def _headers(db, admin):
    from app.auth import create_user_access_token

    return {"Authorization": f"Bearer {create_user_access_token(admin)}"}


def _user_row(db, username):
    return db.query(User).filter(User.username == username).one()


def _stub_adapter(monkeypatch):
    """get_adapter_for_node возвращает стаб; записываются вызовы по узлам."""
    stub = _StubAdapter()
    calls = []

    def fake_get_adapter_for_node(node):
        calls.append(node.id)
        return stub

    monkeypatch.setattr("app.routers.users.get_adapter_for_node", fake_get_adapter_for_node)
    return stub, calls


def _stub_deprovision(monkeypatch):
    def fake_deprovision(session, *, config, actor, notify=False, **_kwargs):
        session.delete(config)
        session.commit()

    monkeypatch.setattr("app.routers.users.deprovision_config", fake_deprovision)


def _make_plan_user(db, node):
    ivan = User(
        username="ivan",
        password_hash="x",
        role=UserRole.user,
        client_base_name="ivan",
        plan_config_indexes=json.dumps([1]),
        desired_protocols=json.dumps(["wireguard"]),
        panel_login_enabled=False,
    )
    db.add(ivan)
    db.commit()
    db.refresh(ivan)
    db.add(UserNodeAssignment(user_id=ivan.id, node_id=node.id))
    config = VpnConfig(
        node_id=node.id,
        client_name="ivan",
        vpn_type=VpnType.wireguard,
        owner_id=ivan.id,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return ivan, config


# --- 1. owner mismatch → 404 (как у missing) ---


def test_d2_owner_mismatch_404(client, db, admin, nodes):
    ivan, config = _make_plan_user(db, nodes[0])
    petr = User(username="petr", password_hash="x", role=UserRole.user, panel_login_enabled=False)
    db.add(petr)
    db.commit()

    for method, path in (
        ("get", f"/api/users/{petr.id}/configs/{config.id}/files"),
        ("delete", f"/api/users/{petr.id}/configs/{config.id}"),
    ):
        response = getattr(client, method)(path, headers=_headers(db, admin))
        assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
        assert response.json()["detail"] == "Конфигурация не найдена", response.text

    # Чужой конфиг не тронут.
    assert db.get(VpnConfig, config.id) is not None


# --- 2. D2 использует узел конфига, не активный ---


def test_d2_uses_config_node_not_active(client, db, admin, nodes, monkeypatch):
    ivan, config = _make_plan_user(db, nodes[0])
    stub, calls = _stub_adapter(monkeypatch)
    _stub_deprovision(monkeypatch)

    response = client.get(
        f"/api/users/{ivan.id}/configs/{config.id}/download?path=client.ovpn",
        headers=_headers(db, admin),
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.text == "-----BEGIN OPENVPN CONFIG-----", response.text
    # Адаптер брали от узла конфига, а не активного узла.
    assert calls == [nodes[0].id], calls
    assert any(call[0] == "read_profile_file" for call in stub.calls), stub.calls


# --- 3. DELETE in-plan config → строка ушла, provision_state = "pending", имена в плане ---


def test_d2_delete_in_plan_sets_pending(client, db, admin, nodes, monkeypatch):
    ivan, config = _make_plan_user(db, nodes[0])
    _stub_adapter(monkeypatch)
    _stub_deprovision(monkeypatch)

    response = client.delete(
        f"/api/users/{ivan.id}/configs/{config.id}", headers=_headers(db, admin)
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    assert db.get(VpnConfig, config.id) is None
    ivan = _user_row(db, "ivan")
    assert ivan.provision_state == "pending"
    assert json.loads(ivan.plan_config_indexes) == [1]


# --- 4. DELETE user → 409 пока активно задание user_provision ---


def test_delete_user_409_while_task_running(client, db, admin, nodes):
    ivan, _ = _make_plan_user(db, nodes[0])
    task_id = background_task_service.create_queued_task(
        "user_provision",
        "Применение плана…",
        created_by_username="admin",
        subject_key=f"user:{ivan.id}",
    )
    background_task_service.update_background_task(task_id, status="running")

    response = client.delete(f"/api/users/{ivan.id}", headers=_headers(db, admin))
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert _user_row(db, "ivan").provision_state != "pending_deletion"


# --- 5. plan user, очистка падает → пользователь остаётся pending_deletion, строка не удалена ---


def test_delete_user_failed_cleanup_stays_pending_deletion(client, db, admin, nodes, monkeypatch):
    ivan, config = _make_plan_user(db, nodes[0])
    _stub_adapter(monkeypatch)

    def boom(session, *, config, actor, notify=False, **_kwargs):
        raise RuntimeError("узел недоступен")

    monkeypatch.setattr("app.services.user_provisioning.deprovision_config", boom)

    response = client.delete(f"/api/users/{ivan.id}", headers=_headers(db, admin))
    assert response.status_code == status.HTTP_202_ACCEPTED, response.text

    ivan = db.query(User).filter_by(id=ivan.id).one()
    assert ivan.provision_state == "pending_deletion"
    assert db.get(User, ivan.id) is not None
    assert db.get(VpnConfig, config.id) is not None


# --- 6. admin telegram-link-code → 200 {code, expires_in}; non-admin 403 ---


def test_telegram_link_code_admin(client, db, admin, nodes):
    ivan, _ = _make_plan_user(db, nodes[0])

    response = client.post(
        f"/api/users/{ivan.id}/telegram-link-code", headers=_headers(db, admin)
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert "code" in body and body["code"]
    assert body["expires_in_seconds"] == 600

    # не-админ не может выдавать код другому пользователю.
    viewer = User(username="viewer", password_hash="x", role=UserRole.user, panel_login_enabled=False)
    db.add(viewer)
    db.commit()
    db.refresh(viewer)
    from app.auth import create_user_access_token

    viewer_headers = {"Authorization": f"Bearer {create_user_access_token(viewer)}"}
    response = client.post(
        f"/api/users/{ivan.id}/telegram-link-code", headers=viewer_headers
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text


# --- 7. user stats shape (пустая traffic БД) ---


def test_user_stats_shape(client, db, admin, nodes):
    ivan, _ = _make_plan_user(db, nodes[0])
    response = client.get(f"/api/users/{ivan.id}/stats?days=30", headers=_headers(db, admin))
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["user_id"] == ivan.id
    assert body["period_days"] == 30
    assert "rows" in body and isinstance(body["rows"], list)
    assert "totals" in body
    totals = body["totals"]
    for key in ("received", "sent", "bytes", "sessions", "period_bytes"):
        assert totals[key] == 0, totals
