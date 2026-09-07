"""Tests for public route-file / QR download endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers import public_download as public_download_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(public_download_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as c:
        yield c


def test_route_download_disabled_returns_404(client):
    with (
        patch("app.routers.public_download.require_openvpn_and_security"),
        patch("app.routers.public_download.is_public_download_enabled", return_value=False),
    ):
        resp = client.get("/api/public/route-download/keenetic")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Not found"


def test_route_download_unknown_router_404(client):
    with (
        patch("app.routers.public_download.require_openvpn_and_security"),
        patch("app.routers.public_download.is_public_download_enabled", return_value=True),
        patch("app.routers.public_download.ip_restriction_service") as ip_svc,
        patch("app.routers.public_download.public_download_rate_limit_service") as rl,
    ):
        ip_svc.get_client_ip.return_value = "203.0.113.10"
        resp = client.get("/api/public/route-download/not-a-router")
    assert resp.status_code == 404
    rl.consume.assert_called_once_with("203.0.113.10")


def test_route_download_success_consumes_rate_limit(client):
    adapter = MagicMock()
    adapter.get_route_result_content.return_value = {
        "filename": "keenetic-routes.conf",
        "content": "routes\n",
    }
    with (
        patch("app.routers.public_download.require_openvpn_and_security"),
        patch("app.routers.public_download.is_public_download_enabled", return_value=True),
        patch("app.routers.public_download.ip_restriction_service") as ip_svc,
        patch("app.routers.public_download.public_download_rate_limit_service") as rl,
        patch("app.routers.public_download.get_active_adapter", return_value=adapter),
        patch("app.routers.public_download.settings") as settings,
        patch("app.routers.public_download.log_action") as log_action,
    ):
        settings.audit_log_enabled = True
        ip_svc.get_client_ip.return_value = "198.51.100.7"
        resp = client.get("/api/public/route-download/keenetic")

    assert resp.status_code == 200
    assert resp.content == b"routes\n"
    assert "keenetic-routes.conf" in resp.headers.get("content-disposition", "")
    rl.consume.assert_called_once_with("198.51.100.7")
    log_action.assert_called_once()
    adapter.get_route_result_content.assert_called_once_with("keenetic_wg")


def test_route_download_rate_limit_propagates(client):
    with (
        patch("app.routers.public_download.require_openvpn_and_security"),
        patch("app.routers.public_download.is_public_download_enabled", return_value=True),
        patch("app.routers.public_download.ip_restriction_service") as ip_svc,
        patch("app.routers.public_download.public_download_rate_limit_service") as rl,
    ):
        ip_svc.get_client_ip.return_value = "203.0.113.99"
        rl.consume.side_effect = HTTPException(status_code=429, detail="too many")
        resp = client.get("/api/public/route-download/mikrotik")

    assert resp.status_code == 429
    assert resp.json()["detail"] == "too many"


def test_qr_download_get_requires_pin_when_configured(client):
    pin_row = MagicMock()
    pin_row.value = "1234"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = pin_row
    client.app.dependency_overrides[get_db] = lambda: db

    resp = client.get("/api/public/qr-download/tok-abc")
    assert resp.status_code == 428
    assert "PIN" in resp.json()["detail"]


def test_qr_download_post_redeems_with_pin(client):
    row = MagicMock()
    row.file_path = "/tmp/alice.ovpn"
    row.config_name = "alice.ovpn"
    node = MagicMock()
    node.id = 1
    adapter = MagicMock()

    with (
        patch("app.routers.public_download._qr_settings", return_value={"ttl_seconds": 60, "max_downloads": 1, "pin": "9999"}),
        patch("app.routers.public_download.QrDownloadService") as Svc,
        patch("app.routers.public_download.get_active_node", return_value=node),
        patch("app.routers.public_download.load_node_remote_hosts", return_value=[]),
        patch("app.routers.public_download.read_profile_file_for_delivery", return_value="client\n"),
        patch("app.routers.public_download.get_active_adapter", return_value=adapter),
    ):
        Svc.return_value.redeem_token.return_value = row
        resp = client.post("/api/public/qr-download/tok-xyz", json={"pin": "9999"})

    assert resp.status_code == 200
    assert resp.content == b"client\n"
    Svc.return_value.redeem_token.assert_called_once()
    kwargs = Svc.return_value.redeem_token.call_args.kwargs
    assert kwargs.get("pin") == "9999"
