"""Tests for event webhooks on UserActionLog."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.models import AppSetting, WebhookDelivery
from app.services.action_log import log_action
from app.services.event_webhooks import event_webhook_service


class _Handler(BaseHTTPRequestHandler):
    status_code = 200
    received: list[bytes] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).received.append(body)
        self.send_response(type(self).status_code)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return


@pytest.fixture()
def mock_http_server():
    _Handler.received = []
    _Handler.status_code = 200
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/hook"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _configure_webhooks(db, url: str, *, events: list[str] | None = None):
    db.add(AppSetting(key="event_webhook_url", value=url))
    db.add(AppSetting(key="event_webhook_secret", value="test-secret"))
    db.add(AppSetting(key="event_webhook_enabled", value="true"))
    db.add(AppSetting(key="event_webhook_events", value=json.dumps(events or ["login_success"])))
    db.commit()


def test_webhook_dispatched_on_log_action(api_test_env, mock_http_server):
    env = api_test_env
    session = env["session_factory"]()
    try:
        _configure_webhooks(session, mock_http_server)
        log_action(
            session,
            action="login_success",
            username="api_admin",
            details="payload test",
            remote_addr="127.0.0.1",
        )
        pending = session.query(WebhookDelivery).filter(WebhookDelivery.status == "pending").count()
        assert pending == 1
    finally:
        session.close()

    with patch("app.services.event_webhooks.SessionLocal", env["session_factory"]):
        processed = event_webhook_service.process_pending_deliveries()
    assert processed == 1
    assert len(_Handler.received) == 1
    payload = json.loads(_Handler.received[0].decode("utf-8"))
    assert payload["event"] == "login_success"
    assert payload["details"] == "payload test"


def test_webhook_retries_on_5xx(api_test_env, mock_http_server, monkeypatch):
    env = api_test_env
    _Handler.status_code = 503
    _Handler.received = []

    monkeypatch.setattr(
        "app.services.event_webhooks.get_settings",
        lambda: type(
            "S",
            (),
            {
                "event_webhook_timeout_seconds": 2.0,
                "event_webhook_max_attempts": 3,
                "event_webhook_retry_interval_seconds": 1,
            },
        )(),
    )

    session = env["session_factory"]()
    try:
        _configure_webhooks(session, mock_http_server)
        log_action(session, action="login_success", username="api_admin")
        row = session.query(WebhookDelivery).first()
        assert row is not None
        delivery_id = row.id
    finally:
        session.close()

    with patch("app.services.event_webhooks.SessionLocal", env["session_factory"]):
        event_webhook_service.process_pending_deliveries()
    assert len(_Handler.received) == 1

    session = env["session_factory"]()
    try:
        row = session.get(WebhookDelivery, delivery_id)
        assert row.status == "pending"
        assert row.attempts == 1
        row.next_retry_at = row.next_retry_at.replace(year=2000)
        session.commit()
    finally:
        session.close()

    with patch("app.services.event_webhooks.SessionLocal", env["session_factory"]):
        event_webhook_service.process_pending_deliveries()
    assert len(_Handler.received) == 2


def test_event_webhook_settings_api(api_test_env, mock_http_server):
    env = api_test_env
    client = TestClient(env["app"])

    get_resp = client.get("/api/security/event-webhooks", headers=env["admin_headers"])
    assert get_resp.status_code == 200
    assert "events" in get_resp.json()

    patch_resp = client.patch(
        "/api/security/event-webhooks",
        headers=env["admin_headers"],
        json={"url": mock_http_server, "secret": "s3cret", "enabled": True},
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["url"] == mock_http_server
    assert body["enabled"] is True
    assert body["secret_configured"] is True
