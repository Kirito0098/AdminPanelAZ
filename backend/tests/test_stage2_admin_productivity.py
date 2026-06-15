"""Stage 2 admin productivity: tags, templates, sessions, bulk ops."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.models import ActiveWebSession, AppSetting, ClientTemplate, User, VpnConfig, VpnType


def _immediate_submit(fn, *args, **kwargs):
    fn(*args, **kwargs)


def _set_active_node(session_factory, node_id: int) -> None:
    db = session_factory()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "active_node_id").first()
        if row:
            row.value = str(node_id)
        else:
            db.add(AppSetting(key="active_node_id", value=str(node_id)))
        db.commit()
    finally:
        db.close()


def test_config_tags_crud_and_assign(api_test_env):
    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]
    node = api_test_env["node"]
    _set_active_node(api_test_env["session_factory"], node.id)

    create = client.post("/api/config-tags", headers=headers, json={"name": "vip", "color": "#ff0000"})
    assert create.status_code == 201
    tag_id = create.json()["id"]

    listed = client.get("/api/config-tags", headers=headers)
    assert listed.status_code == 200
    assert any(t["name"] == "vip" for t in listed.json())

    db = api_test_env["session_factory"]()
    admin = db.query(User).filter(User.username == "api_admin").first()
    cfg = VpnConfig(
        node_id=node.id,
        client_name="tagged-client",
        vpn_type=VpnType.openvpn,
        owner_id=admin.id,
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    config_id = cfg.id
    db.close()

    assign = client.put(
        f"/api/config-tags/configs/{config_id}/tags",
        headers=headers,
        json={"tag_ids": [tag_id]},
    )
    assert assign.status_code == 200
    assert assign.json()[0]["name"] == "vip"

    configs = client.get("/api/configs", headers=headers, params={"tag_ids": [tag_id]})
    assert configs.status_code == 200
    assert len(configs.json()) == 1
    assert configs.json()[0]["client_name"] == "tagged-client"


def test_client_templates_list_and_apply(api_test_env):
    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]
    node = api_test_env["node"]
    _set_active_node(api_test_env["session_factory"], node.id)

    db = api_test_env["session_factory"]()
    db.add(
        ClientTemplate(
            node_id=node.id,
            name="Test OVPN",
            vpn_type=VpnType.openvpn,
            cert_expire_days=3650,
            sort_order=1,
            is_builtin=True,
        )
    )
    db.commit()
    tpl = db.query(ClientTemplate).filter(ClientTemplate.node_id == node.id).first()
    tpl_id = tpl.id
    db.close()

    listed = client.get("/api/client-templates", headers=headers)
    assert listed.status_code == 200
    assert any(t["name"] == "Test OVPN" for t in listed.json())

    mock = api_test_env["mock_adapter"]
    mock.add_openvpn_client.return_value = None

    applied = client.post(
        f"/api/client-templates/{tpl_id}/apply",
        headers=headers,
        json={"client_name": "from-template"},
    )
    assert applied.status_code == 201
    assert applied.json()["client_name"] == "from-template"
    mock.add_openvpn_client.assert_called()


def test_active_sessions_list_and_revoke(api_test_env):
    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]

    db = api_test_env["session_factory"]()
    db.add(
        ActiveWebSession(
            session_id="abc123",
            username="api_admin",
            remote_addr="10.0.0.1",
            user_agent="TestAgent",
            created_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
    )
    db.commit()
    db.close()

    listed = client.get("/api/security/active-sessions", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["session_id"] == "abc123"

    revoked = client.delete("/api/security/active-sessions/abc123", headers=headers)
    assert revoked.status_code == 200

    heartbeat = client.get(
        "/api/session-heartbeat",
        headers={**headers, "X-Web-Session-Id": "abc123"},
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["revoked"] is True


def test_bulk_config_op_background_task(api_test_env):
    client = TestClient(api_test_env["app"])
    headers = api_test_env["admin_headers"]
    node = api_test_env["node"]
    session_factory = api_test_env["session_factory"]
    _set_active_node(session_factory, node.id)

    db = session_factory()
    admin = db.query(User).filter(User.username == "api_admin").first()
    ids = []
    for i in range(3):
        cfg = VpnConfig(
            node_id=node.id,
            client_name=f"bulk-{i}",
            vpn_type=VpnType.wireguard,
            owner_id=admin.id,
        )
        db.add(cfg)
        db.flush()
        ids.append(cfg.id)
    db.commit()
    db.close()

    mock = api_test_env["mock_adapter"]
    mock.delete_wireguard_client.return_value = None
    exec_mock = MagicMock()
    exec_mock.submit = _immediate_submit

    with (
        patch("app.services.background_tasks._EXECUTOR", exec_mock),
        patch("app.services.bulk_config_ops.SessionLocal", session_factory),
    ):
        queued = client.post(
            "/api/configs/bulk",
            headers=headers,
            json={"operation": "delete", "config_ids": ids},
        )
    assert queued.status_code == 202
    task_id = queued.json()["task_id"]

    status = client.get(f"/api/tasks/{task_id}", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    mock.delete_wireguard_client.assert_called()

    db = session_factory()
    remaining = db.query(VpnConfig).filter(VpnConfig.id.in_(ids)).count()
    db.close()
    assert remaining == 0
