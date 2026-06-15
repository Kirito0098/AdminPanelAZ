"""Tests for VPN config CSV import/export."""

import csv
import io
import time
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.models import User, VpnConfig, VpnType


def _client(env):
    return TestClient(env["app"])


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["client_name", "vpn_type", "owner_username", "cert_expire_days", "description"],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def test_export_configs_csv(api_test_env):
    env = api_test_env
    session = env["session_factory"]()
    try:
        admin = session.query(User).filter(User.username == "api_admin").first()
        session.add(
            VpnConfig(
                node_id=env["node"].id,
                client_name="export-me",
                vpn_type=VpnType.openvpn,
                owner_id=admin.id,
                cert_expire_days=365,
            )
        )
        session.commit()
    finally:
        session.close()

    response = _client(env).get("/api/configs/export", headers=env["admin_headers"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][1] == "client_name"
    assert any(r[1] == "export-me" for r in rows[1:])


def test_import_configs_csv_sync(api_test_env, monkeypatch):
    env = api_test_env
    monkeypatch.setattr("app.services.config_csv_ops.get_settings", lambda: type("S", (), {"config_csv_import_async_threshold": 100})())

    mock_adapter = env["mock_adapter"]
    mock_adapter.add_openvpn_client.return_value = None

    content = _csv_bytes(
        [
            {"client_name": "csv-sync-1", "vpn_type": "openvpn", "owner_username": "api_admin", "cert_expire_days": "30", "description": ""},
            {"client_name": "csv-sync-2", "vpn_type": "wireguard", "owner_username": "api_admin", "cert_expire_days": "", "description": "note"},
        ]
    )

    with patch("app.services.config_csv_ops.get_active_adapter", return_value=mock_adapter), patch(
        "app.services.config_csv_ops.SessionLocal", env["session_factory"]
    ):
        response = _client(env).post(
            "/api/configs/import",
            headers=env["admin_headers"],
            files={"file": ("clients.csv", content, "text/csv")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["async"] is False
    assert body["result"]["total"] == 2
    assert len(body["result"]["succeeded"]) == 2


def test_import_configs_csv_background_for_large_batch(api_test_env, monkeypatch):
    env = api_test_env
    monkeypatch.setattr("app.services.config_csv_ops.get_settings", lambda: type("S", (), {"config_csv_import_async_threshold": 2})())

    rows = [
        {
            "client_name": f"bulk-{i}",
            "vpn_type": "openvpn",
            "owner_username": "api_admin",
            "cert_expire_days": "",
            "description": "",
        }
        for i in range(3)
    ]
    content = _csv_bytes(rows)

    mock_adapter = env["mock_adapter"]
    mock_adapter.add_openvpn_client.return_value = None

    with patch("app.services.config_csv_ops.get_active_adapter", return_value=mock_adapter), patch(
        "app.services.config_csv_ops.SessionLocal", env["session_factory"]
    ):
        response = _client(env).post(
            "/api/configs/import",
            headers=env["admin_headers"],
            files={"file": ("clients.csv", content, "text/csv")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["queued"] is True
    task_id = body["task_id"]

    deadline = time.time() + 10
    status = None
    while time.time() < deadline:
        status = _client(env).get(f"/api/tasks/{task_id}", headers=env["admin_headers"]).json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.2)

    assert status is not None
    assert status["status"] == "completed"
    assert status["task_type"] == "config_csv_import"
