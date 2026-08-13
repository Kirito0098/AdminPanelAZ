import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import require_admin
from app.database import get_db
from app.models import NodeStatus, User
from app.routers import maintenance as maintenance_router
from app.services import server_reboot as sr


@pytest.fixture(autouse=True)
def _clean():
    sr.clear_all_for_tests()
    yield
    sr.clear_all_for_tests()


def _admin():
    u = MagicMock(spec=User)
    u.username = "admin"
    u.id = 1
    return u


def _node(*, node_id=10, name="vpn-a", status=NodeStatus.online):
    node = MagicMock()
    node.id = node_id
    node.name = name
    node.status = status
    node.node_kind = "vpn"
    return node


def _db_with_node(node):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = node
    return db


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(maintenance_router.router, prefix="/api")
    app.dependency_overrides[require_admin] = _admin
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as c:
        yield c


def test_schedule_rejects_bad_confirm(client):
    resp = client.post("/api/settings/reboot", json={"node_id": 1, "confirm": "reboot"})
    assert resp.status_code == 400


def test_schedule_missing_node_404(client):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.routers.maintenance.admin_notify_service"), patch("app.routers.maintenance.log_action"):
        resp = client.post("/api/settings/reboot", json={"node_id": 999, "confirm": "REBOOT"})
    assert resp.status_code == 404


def test_schedule_rejects_proxy_node(client):
    node = _node()
    node.node_kind = "proxy"
    client.app.dependency_overrides[get_db] = lambda: _db_with_node(node)

    with patch("app.routers.maintenance.admin_notify_service"), patch("app.routers.maintenance.log_action"):
        resp = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
    assert resp.status_code == 400
    assert "VPN" in resp.json()["detail"]


def test_schedule_duplicate_409(client):
    node = _node()
    client.app.dependency_overrides[get_db] = lambda: _db_with_node(node)

    with patch("app.routers.maintenance.get_adapter_for_node") as get_ad, patch(
        "app.routers.maintenance.admin_notify_service"
    ), patch("app.routers.maintenance.log_action"):
        adapter = MagicMock()
        adapter.reboot = MagicMock(return_value="ok")
        get_ad.return_value = adapter

        first = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
        assert first.status_code == 200
        second = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
        assert second.status_code == 409


def test_schedule_and_cancel(client):
    node = _node()
    client.app.dependency_overrides[get_db] = lambda: _db_with_node(node)

    with patch("app.routers.maintenance.get_adapter_for_node") as get_ad, patch(
        "app.routers.maintenance.admin_notify_service"
    ), patch("app.routers.maintenance.log_action"):
        adapter = MagicMock()
        adapter.reboot = MagicMock(return_value="ok")
        get_ad.return_value = adapter
        resp = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["node_id"] == 10
        assert body["delay_seconds"] == 15
        rid = body["reboot_id"]
        cancel = client.post(f"/api/settings/reboot/{rid}/cancel")
        assert cancel.status_code == 200
        adapter.reboot.assert_not_called()


def test_schedule_offline_node_includes_warning(client):
    node = _node(status=NodeStatus.offline)
    client.app.dependency_overrides[get_db] = lambda: _db_with_node(node)

    with patch("app.routers.maintenance.get_adapter_for_node"), patch(
        "app.routers.maintenance.admin_notify_service"
    ), patch("app.routers.maintenance.log_action"):
        resp = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
    assert resp.status_code == 200
    warning = resp.json()["warning"]
    assert warning
    assert "offline" in warning.lower() or "недоступ" in warning.lower()


def test_schedule_unknown_node_includes_warning(client):
    node = _node(status=NodeStatus.unknown)
    client.app.dependency_overrides[get_db] = lambda: _db_with_node(node)

    with patch("app.routers.maintenance.get_adapter_for_node"), patch(
        "app.routers.maintenance.admin_notify_service"
    ), patch("app.routers.maintenance.log_action"):
        resp = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
    assert resp.status_code == 200
    assert resp.json()["warning"]


def test_schedule_calls_audit_and_notify(client):
    node = _node()
    client.app.dependency_overrides[get_db] = lambda: _db_with_node(node)

    with patch("app.routers.maintenance.get_adapter_for_node"), patch(
        "app.routers.maintenance.admin_notify_service"
    ) as notify, patch("app.routers.maintenance.log_action") as log_action:
        resp = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
    assert resp.status_code == 200
    log_action.assert_called_once()
    assert log_action.call_args.kwargs["action"] == "settings_reboot_schedule"
    notify.send_settings_change.assert_called_once()
    assert notify.send_settings_change.call_args.kwargs["settings_key"] == "settings_reboot_schedule"


def test_cancel_not_pending_returns_409(client):
    node = _node()
    client.app.dependency_overrides[get_db] = lambda: _db_with_node(node)

    with patch("app.routers.maintenance.get_adapter_for_node"), patch(
        "app.routers.maintenance.admin_notify_service"
    ), patch("app.routers.maintenance.log_action"):
        resp = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
        rid = resp.json()["reboot_id"]
        first_cancel = client.post(f"/api/settings/reboot/{rid}/cancel")
        assert first_cancel.status_code == 200
        second_cancel = client.post(f"/api/settings/reboot/{rid}/cancel")
        assert second_cancel.status_code == 409


def test_execute_failure_still_audits(client):
    node = _node()
    worker_node = _node()
    db = _db_with_node(node)
    client.app.dependency_overrides[get_db] = lambda: db

    with patch("app.routers.maintenance.get_adapter_for_node") as get_ad, patch(
        "app.routers.maintenance.admin_notify_service"
    ) as notify, patch("app.routers.maintenance.log_action") as log_action, patch(
        "app.database.SessionLocal"
    ) as session_local, patch("app.services.server_reboot.DELAY_SECONDS", 0.05):
        adapter = MagicMock()
        adapter.reboot = MagicMock(side_effect=RuntimeError("boom"))
        get_ad.return_value = adapter
        worker_db = MagicMock()
        worker_db.query.return_value.filter.return_value.first.return_value = worker_node
        session_local.return_value = worker_db

        resp = client.post("/api/settings/reboot", json={"node_id": 10, "confirm": "REBOOT"})
        assert resp.status_code == 200
        time.sleep(0.15)

    execute_logs = [
        c for c in log_action.call_args_list if c.kwargs.get("action") == "settings_reboot_execute"
    ]
    assert len(execute_logs) == 1
    assert "failed" in execute_logs[0].kwargs["details"]
    execute_notifies = [
        c
        for c in notify.send_settings_change.call_args_list
        if c.kwargs.get("settings_key") == "settings_reboot_execute"
    ]
    assert len(execute_notifies) == 1
    assert "failed" in execute_notifies[0].kwargs["details"]
    assert "ошибка" in execute_notifies[0].kwargs["subject_name"]


def test_pending_list(client):
    with patch("app.routers.maintenance.admin_notify_service"), patch(
        "app.routers.maintenance.log_action"
    ), patch("app.routers.maintenance.get_adapter_for_node"):
        sr.schedule_reboot(node_id=1, node_name="n", scheduled_by="a", execute_fn=MagicMock(), delay_seconds=5)
        resp = client.get("/api/settings/reboot/pending")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1


def test_pending_list_recomputes_offline_warning(client):
    node = _node(status=NodeStatus.offline)
    client.app.dependency_overrides[get_db] = lambda: _db_with_node(node)

    with patch("app.routers.maintenance.admin_notify_service"), patch(
        "app.routers.maintenance.log_action"
    ), patch("app.routers.maintenance.get_adapter_for_node"):
        sr.schedule_reboot(
            node_id=10, node_name="vpn-a", scheduled_by="a", execute_fn=MagicMock(), delay_seconds=5
        )
        resp = client.get("/api/settings/reboot/pending")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["warning"]
