"""Tests for panel enable-mtls orchestration."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_password_hash
from app.config import Settings
from app.database import Base
from app.models import Node, NodeStatus, User, UserRole
from app.services.node_manager import store_api_key
from app.services.node_mtls_certs import MtlsProvisionBundle


@pytest.fixture()
def mtls_env(tmp_path, monkeypatch):
    mtls_dir = tmp_path / "mtls"
    settings = Settings(
        node_agent_mtls_dir=mtls_dir,
        node_agent_mtls_ca_cert=str(mtls_dir / "ca.crt"),
        node_agent_mtls_client_cert=str(mtls_dir / "panel.crt"),
        node_agent_mtls_client_key=str(mtls_dir / "panel.key"),
        audit_log_enabled=True,
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.node_mtls_certs.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.node_mtls.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.node_mtls_provision.get_settings", lambda: settings)
    return settings


@pytest.fixture()
def db_with_nodes(tmp_path, mtls_env):
    db_path = tmp_path / "provision.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    admin = User(
        username="admin",
        password_hash=get_password_hash("secret"),
        role=UserRole.admin,
        is_active=True,
    )
    local = Node(
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    api_key = "k" * 32
    key_hash, key_encrypted = store_api_key("", api_key)
    remote = Node(
        name="remote-vpn",
        host="10.0.0.50",
        port=9100,
        is_local=False,
        status=NodeStatus.online,
        api_key_hash=key_hash,
        api_key_encrypted=key_encrypted,
        node_metadata="{}",
    )
    session.add_all([admin, local, remote])
    session.commit()
    yield session, admin, local, remote, api_key
    session.close()


def _sample_bundle() -> MtlsProvisionBundle:
    cert = "-----BEGIN CERTIFICATE-----\n" + "A" * 80 + "\n-----END CERTIFICATE-----\n"
    key = "-----BEGIN RSA PRIVATE KEY-----\n" + "B" * 80 + "\n-----END RSA PRIVATE KEY-----\n"
    return MtlsProvisionBundle(ca_pem=cert, agent_cert_pem=cert, agent_key_pem=key)


def test_enable_mtls_success(db_with_nodes, mtls_env):
    from app.services.node_mtls_provision import enable_mtls

    session, admin, _local, remote, _api_key = db_with_nodes
    mock_adapter = MagicMock()
    mock_adapter.provision_mtls.return_value = {"success": True, "message": "ok", "mtls_enabled": True}

    with patch("app.services.node_mtls_provision.check_node_health") as health_mock, patch(
        "app.services.node_mtls_provision.RemoteNodeAdapter", return_value=mock_adapter
    ), patch("app.services.node_mtls_provision.update_node_from_health"), patch(
        "app.services.node_mtls_provision.log_action"
    ) as log_mock:
        health_mock.side_effect = [
            {"status": "online"},
            {"status": "online", "hostname": "vpn1"},
        ]
        result = enable_mtls(session, remote, admin)

    assert result.mtls_enabled is True
    meta = json.loads(result.node_metadata)
    assert "mtls_provisioned_at" in meta
    mock_adapter.provision_mtls.assert_called_once()
    mock_adapter.close.assert_called_once()
    log_mock.assert_called_once()
    assert log_mock.call_args.kwargs["action"] == "node_mtls_enable"


def test_enable_mtls_rolls_back_on_https_health_failure(db_with_nodes, mtls_env):
    from app.services.node_mtls_provision import enable_mtls

    session, admin, _local, remote, _api_key = db_with_nodes
    mock_adapter = MagicMock()
    mock_adapter.provision_mtls.return_value = {"success": True, "message": "ok", "mtls_enabled": True}

    with patch("app.services.node_mtls_provision.check_node_health") as health_mock, patch(
        "app.services.node_mtls_provision._wait_for_mtls_health",
        return_value={"status": "offline", "error": "SSL handshake failed"},
    ), patch(
        "app.services.node_mtls_provision.RemoteNodeAdapter", return_value=mock_adapter
    ):
        health_mock.return_value = {"status": "online"}
        with pytest.raises(HTTPException) as exc_info:
            enable_mtls(session, remote, admin)

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    session.refresh(remote)
    assert remote.mtls_enabled is False


def test_enable_mtls_rejects_local_node(db_with_nodes):
    from app.services.node_mtls_provision import enable_mtls

    session, admin, local, _remote, _api_key = db_with_nodes
    with pytest.raises(ValueError, match="Локальный узел"):
        enable_mtls(session, local, admin)


def test_enable_mtls_rejects_offline_node(db_with_nodes):
    from app.services.node_mtls_provision import enable_mtls

    session, admin, _local, remote, _api_key = db_with_nodes
    with patch(
        "app.services.node_mtls_provision.check_node_health",
        return_value={"status": "offline", "error": "connection refused"},
    ):
        with pytest.raises(HTTPException) as exc_info:
            enable_mtls(session, remote, admin)

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_mtls_status_api_requires_admin(api_test_env, tmp_path):
    from fastapi.testclient import TestClient

    env = api_test_env
    env["settings"].enforce_https = False
    mtls_dir = tmp_path / "panel_mtls"
    env["settings"].node_agent_mtls_dir = mtls_dir
    client = TestClient(env["app"])

    with patch("app.services.node_mtls_certs.get_settings", return_value=env["settings"]):
        resp = client.get("/api/nodes/mtls/status")
        assert resp.status_code == 401

        resp = client.get("/api/nodes/mtls/status", headers=env["admin_headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["ready"] is False
        assert body["writable"] is True
        assert body["mtls_dir"] == str(mtls_dir)
        assert body["ca_cert"] == str(mtls_dir / "ca.crt")
        assert body["agent_certs_count"] == 0


def test_enable_mtls_api_400_for_local(api_test_env):
    from fastapi.testclient import TestClient

    env = api_test_env
    env["settings"].enforce_https = False
    local = env["node"]
    client = TestClient(env["app"])

    resp = client.post(
        f"/api/nodes/{local.id}/enable-mtls",
        headers=env["admin_headers"],
    )
    assert resp.status_code == 400
    assert "Локальный узел" in resp.json()["detail"]


def test_enable_mtls_api_503_for_offline(api_test_env):
    from fastapi.testclient import TestClient

    from app.models import Node, NodeStatus
    from app.services.node_manager import store_api_key

    env = api_test_env
    env["settings"].enforce_https = False
    session = env["session_factory"]()
    api_key = "x" * 32
    key_hash, key_encrypted = store_api_key("", api_key)
    remote = Node(
        name="offline-remote",
        host="10.0.0.99",
        port=9100,
        is_local=False,
        status=NodeStatus.offline,
        api_key_hash=key_hash,
        api_key_encrypted=key_encrypted,
    )
    session.add(remote)
    session.commit()
    node_id = remote.id
    session.close()

    client = TestClient(env["app"])
    with patch(
        "app.services.node_mtls_provision.check_node_health",
        return_value={"status": "offline", "error": "timeout"},
    ):
        resp = client.post(
            f"/api/nodes/{node_id}/enable-mtls",
            headers=env["admin_headers"],
        )

    assert resp.status_code == 503


def test_disable_mtls_clears_flag(db_with_nodes):
    from app.services.node_mtls_provision import disable_mtls

    session, _admin, _local, remote, _api_key = db_with_nodes
    remote.mtls_enabled = True
    session.commit()

    result = disable_mtls(session, remote)
    assert result.mtls_enabled is False


def test_remote_adapter_provision_mtls_calls_endpoint():
    from app.services.node_adapter import RemoteNodeAdapter

    adapter = RemoteNodeAdapter("10.0.0.1", 9100, "k" * 32, mtls_enabled=False)
    bundle = _sample_bundle()
    provision_result = {"success": True, "message": "ok", "mtls_enabled": True}
    restart_result = {"success": True, "message": "scheduled", "restarting": True}

    with patch.object(adapter, "_request", side_effect=[provision_result, restart_result]) as request_mock:
        result = adapter.provision_mtls(bundle)

    assert result["success"] is True
    assert result["restart"] == restart_result
    assert request_mock.call_count == 2
    request_mock.assert_any_call(
        "POST",
        "/system/provision-mtls",
        json={
            "ca_pem": bundle.ca_pem,
            "agent_cert_pem": bundle.agent_cert_pem,
            "agent_key_pem": bundle.agent_key_pem,
            "restart": False,
        },
        timeout=120.0,
    )
    request_mock.assert_any_call(
        "POST",
        "/system/restart-agent",
        json={},
        timeout=30.0,
    )
