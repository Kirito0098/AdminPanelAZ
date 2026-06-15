"""Tests for full audit stream (SIEM) export."""

import json
import socket
import threading
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

pytest_plugins = ["tests.test_event_webhooks"]

from app.models import AppSetting, UserActionLog, WebhookDelivery
from app.services.action_log import log_action
from app.services.audit_stream import audit_stream_service
from app.services.event_webhooks import event_webhook_service


@pytest.fixture()
def udp_receiver():
    received: list[bytes] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    stop = threading.Event()

    def _loop():
        sock.settimeout(0.5)
        while not stop.is_set():
            try:
                data, _ = sock.recvfrom(65535)
                received.append(data)
            except TimeoutError:
                continue
            except OSError:
                break

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    try:
        yield port, received
    finally:
        stop.set()
        thread.join(timeout=2)
        sock.close()


def _configure_audit_stream(
    db,
    *,
    mode: str = "http",
    http_url: str = "",
    syslog_host: str = "",
    syslog_port: int = 514,
):
    db.add(AppSetting(key="audit_stream_enabled", value="true"))
    db.add(AppSetting(key="audit_stream_mode", value=mode))
    if http_url:
        db.add(AppSetting(key="audit_stream_http_url", value=http_url))
    if syslog_host:
        db.add(AppSetting(key="audit_stream_syslog_host", value=syslog_host))
        db.add(AppSetting(key="audit_stream_syslog_port", value=str(syslog_port)))
        db.add(AppSetting(key="audit_stream_syslog_protocol", value="udp"))
    db.add(AppSetting(key="audit_stream_format", value="json"))
    db.commit()


def test_audit_stream_enqueues_all_log_actions(api_test_env, mock_http_server):
    env = api_test_env
    session = env["session_factory"]()
    try:
        _configure_audit_stream(session, http_url=mock_http_server)
        log_action(session, action="user_create", username="api_admin", details="created")
        pending = session.query(WebhookDelivery).filter(WebhookDelivery.destination_type == "http").count()
        assert pending == 1
    finally:
        session.close()


def test_audit_stream_http_payload_shape(api_test_env, mock_http_server):
    from tests.test_event_webhooks import _Handler

    env = api_test_env
    _Handler.received = []
    session = env["session_factory"]()
    try:
        _configure_audit_stream(session, http_url=mock_http_server)
        log_action(session, action="login_success", username="api_admin", remote_addr="10.0.0.2")
    finally:
        session.close()

    with patch("app.services.event_webhooks.SessionLocal", env["session_factory"]):
        event_webhook_service.process_pending_deliveries()

    assert len(_Handler.received) == 1
    payload = json.loads(_Handler.received[0].decode("utf-8"))
    assert payload["event.action"] == "login_success"
    assert payload["source.ip"] == "10.0.0.2"


def test_audit_stream_syslog_formatter():
    row = UserActionLog(
        id=1,
        action="backup_restore",
        username="admin",
        remote_addr="127.0.0.1",
        details="ok",
        created_at=datetime.utcnow(),
    )
    payload = audit_stream_service.build_payload(row)
    cef = audit_stream_service.format_message(payload, "cef")
    assert cef.startswith("CEF:")
    assert "backup_restore" in cef


def test_audit_stream_syslog_delivery(api_test_env, udp_receiver):
    env = api_test_env
    port, received = udp_receiver
    session = env["session_factory"]()
    try:
        _configure_audit_stream(session, mode="syslog", syslog_host="127.0.0.1", syslog_port=port)
        log_action(session, action="security_settings_update", username="api_admin")
        row = session.query(WebhookDelivery).filter(WebhookDelivery.destination_type == "syslog").first()
        assert row is not None
    finally:
        session.close()

    with patch("app.services.event_webhooks.SessionLocal", env["session_factory"]):
        event_webhook_service.process_pending_deliveries()

    assert len(received) == 1
    data = json.loads(received[0].decode("utf-8"))
    assert data["event.action"] == "security_settings_update"


def test_audit_stream_settings_api(api_test_env, mock_http_server):
    env = api_test_env
    client = TestClient(env["app"])

    get_resp = client.get("/api/security/audit-stream", headers=env["admin_headers"])
    assert get_resp.status_code == 200
    assert get_resp.json()["mode"] == "http"

    patch_resp = client.patch(
        "/api/security/audit-stream",
        headers=env["admin_headers"],
        json={"enabled": True, "mode": "both", "http_url": mock_http_server, "syslog_host": "127.0.0.1"},
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["enabled"] is True
    assert body["mode"] == "both"
