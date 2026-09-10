"""Tests for client portal domain, tokens, and public download."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.models import ClientPortalToken, VpnConfig, VpnType
from app.routers import public_portal as public_portal_router
from app.services import client_portal as portal


def test_normalize_portal_domain_strips_scheme_and_path():
    assert portal.normalize_portal_domain("https://Sub.Example.com/foo") == "sub.example.com"
    assert portal.normalize_portal_domain("sub.example.com:8443") == "sub.example.com"
    assert portal.normalize_portal_domain("") == ""
    with pytest.raises(ValueError):
        portal.normalize_portal_domain("not a host")


def test_openvpn_import_url_format():
    url = portal.openvpn_import_url("https://sub.example.com/api/public/portal/tok/download?path=a.ovpn")
    assert url.startswith("openvpn://import-profile/https://")


def test_resolve_portal_base_url_none_without_domain():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert portal.resolve_portal_base_url(db) is None


def test_resolve_portal_base_url_with_domain():
    db = MagicMock()
    row = MagicMock()
    row.value = "sub.example.com"
    db.query.return_value.filter.return_value.first.return_value = row
    with patch("app.services.client_portal.get_settings") as gs:
        gs.return_value.https_public_port = 443
        gs.return_value.access_path = ""
        assert portal.resolve_portal_base_url(db) == "https://sub.example.com"


def test_assert_portal_host_mismatch():
    db = MagicMock()
    row = MagicMock()
    row.value = "sub.example.com"
    db.query.return_value.filter.return_value.first.return_value = row
    with pytest.raises(HTTPException) as ei:
        portal.assert_portal_host(db, "panel.example.com")
    assert ei.value.status_code == 404


def test_get_valid_portal_token_revoked():
    db = MagicMock()
    row = ClientPortalToken(
        id=1,
        token="abc",
        node_id=1,
        client_name="alice",
        revoked_at=datetime.utcnow(),
    )
    db.query.return_value.filter.return_value.first.return_value = row
    with pytest.raises(HTTPException) as ei:
        portal.get_valid_portal_token(db, "abc")
    assert ei.value.status_code == 410


@pytest.fixture
def public_client():
    app = FastAPI()
    app.include_router(public_portal_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as c:
        yield c


def test_public_meta_requires_matching_host(public_client):
    db = MagicMock()
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host", side_effect=HTTPException(status_code=404, detail="Not found")),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service"),
    ):
        feats.return_value.is_enabled.return_value = True
        ip_svc.get_client_ip.return_value = "203.0.113.1"
        public_client.app.dependency_overrides[get_db] = lambda: db
        resp = public_client.get("/api/public/portal/tok", headers={"Host": "wrong.example.com"})
    assert resp.status_code == 404


def test_public_download_returns_attachment(public_client):
    token_row = ClientPortalToken(id=1, token="tok", node_id=1, client_name="alice", revoked_at=None)
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service") as rl,
        patch("app.routers.public_portal.get_valid_portal_token", return_value=token_row),
        patch("app.routers.public_portal.read_portal_profile", return_value=("alice.ovpn", b"client\n")),
    ):
        feats.return_value.is_enabled.return_value = True
        ip_svc.get_client_ip.return_value = "198.51.100.1"
        resp = public_client.get(
            "/api/public/portal/tok/download",
            params={"path": "/tmp/alice.ovpn"},
            headers={"Host": "sub.example.com"},
        )
    assert resp.status_code == 200
    assert resp.content == b"client\n"
    assert "alice.ovpn" in resp.headers.get("content-disposition", "")
    rl.consume.assert_called_once_with("198.51.100.1")


def test_link_response_builds_page_url():
    db = MagicMock()
    row = MagicMock()
    row.value = "sub.example.com"
    db.query.return_value.filter.return_value.first.return_value = row
    token = ClientPortalToken(token="XxYy", node_id=1, client_name="bob", revoked_at=None)
    with patch("app.services.client_portal.get_settings") as gs:
        gs.return_value.https_public_port = 443
        gs.return_value.access_path = ""
        payload = portal.link_response(db, token)
    assert payload["url"] == "https://sub.example.com/p/XxYy"
    assert payload["token"] == "XxYy"
