"""Tests for client portal domain, tokens, and public download."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.auth import require_admin
from app.database import get_db
from app.models import ClientPortalToken, UserPortalToken, VpnConfig, VpnType
from app.routers import client_portal as client_portal_router
from app.routers import public_portal as public_portal_router
from app.services import client_portal as portal
from app.services import unlock_codes


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


def test_resolve_portal_base_url_none_when_not_ready():
    db = MagicMock()
    row = MagicMock()
    row.value = "sub.example.com"
    db.query.return_value.filter.return_value.first.return_value = row
    with (
        patch("app.services.client_portal.get_settings") as gs,
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.panel_publish_info.resolve_panel_publish_mode", return_value="behind_nginx"),
        patch("app.services.panel_publish_info.resolve_active_publish_mode_key", return_value="nginx_le"),
        patch("app.services.panel_publish_info.build_portal_publish_status") as bps,
    ):
        gs.return_value.domain = "panel.example.com"
        gs.return_value.https_public_port = 443
        env = env_cls.return_value
        env.get_env_value.side_effect = lambda key, default="": {
            "DOMAIN": "panel.example.com",
            "SSL_CERT": "",
            "BEHIND_NGINX": "1",
            "USE_HTTPS": "1",
            "BACKEND_HOST": "127.0.0.1",
            "BACKEND_PORT": "8000",
            "HTTPS_PUBLIC_PORT": "443",
            "PUBLISH_MODE": "nginx_le",
        }.get(key, default)
        bps.return_value = {"portal_ready": False, "portal_access_url": ""}
        assert portal.resolve_portal_base_url(db) is None


def test_resolve_portal_base_url_with_domain_when_ready():
    db = MagicMock()
    row = MagicMock()
    row.value = "sub.example.com"
    db.query.return_value.filter.return_value.first.return_value = row
    with (
        patch("app.services.client_portal.get_settings") as gs,
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.panel_publish_info.resolve_panel_publish_mode", return_value="behind_nginx"),
        patch("app.services.panel_publish_info.resolve_active_publish_mode_key", return_value="nginx_le"),
        patch("app.services.panel_publish_info.build_portal_publish_status") as bps,
    ):
        gs.return_value.domain = "panel.example.com"
        gs.return_value.https_public_port = 443
        gs.return_value.access_path = ""
        env = env_cls.return_value
        env.get_env_value.side_effect = lambda key, default="": {
            "DOMAIN": "panel.example.com",
            "SSL_CERT": "/etc/ssl/cert.pem",
            "BEHIND_NGINX": "1",
            "USE_HTTPS": "1",
            "BACKEND_HOST": "127.0.0.1",
            "BACKEND_PORT": "8000",
            "HTTPS_PUBLIC_PORT": "443",
            "PUBLISH_MODE": "nginx_le",
        }.get(key, default)
        bps.return_value = {"portal_ready": True, "portal_access_url": "https://sub.example.com/"}
        assert portal.resolve_portal_base_url(db) == "https://sub.example.com"


def test_resolve_portal_base_url_accepts_legacy_access_url_key():
    """Older mocks / callers may still pass access_url; prefer portal_access_url."""
    db = MagicMock()
    row = MagicMock()
    row.value = "sub.example.com"
    db.query.return_value.filter.return_value.first.return_value = row
    with (
        patch("app.services.client_portal.get_settings") as gs,
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.panel_publish_info.resolve_panel_publish_mode", return_value="behind_nginx"),
        patch("app.services.panel_publish_info.resolve_active_publish_mode_key", return_value="nginx_le"),
        patch("app.services.panel_publish_info.build_portal_publish_status") as bps,
    ):
        gs.return_value.domain = "panel.example.com"
        gs.return_value.https_public_port = 443
        gs.return_value.access_path = ""
        env = env_cls.return_value
        env.get_env_value.side_effect = lambda key, default="": {
            "DOMAIN": "panel.example.com",
            "SSL_CERT": "/etc/ssl/cert.pem",
            "BEHIND_NGINX": "1",
            "USE_HTTPS": "1",
            "BACKEND_HOST": "127.0.0.1",
            "BACKEND_PORT": "8000",
            "HTTPS_PUBLIC_PORT": "443",
            "PUBLISH_MODE": "nginx_le",
        }.get(key, default)
        bps.return_value = {"portal_ready": True, "access_url": "https://legacy.example.com/"}
        assert portal.resolve_portal_base_url(db) == "https://legacy.example.com"


def test_resolve_portal_base_url_http_direct_unsupported():
    """Unsupported publish modes never yield a portal base URL."""
    db = MagicMock()
    row = MagicMock()
    row.value = "portal.example.com"
    db.query.return_value.filter.return_value.first.return_value = row
    with (
        patch("app.services.client_portal.get_settings") as gs,
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.panel_publish_info.resolve_panel_publish_mode", return_value="direct_http"),
        patch("app.services.panel_publish_info.resolve_active_publish_mode_key", return_value="http_direct"),
        patch("app.services.panel_publish_info.build_portal_publish_status") as bps,
    ):
        gs.return_value.domain = ""
        gs.return_value.https_public_port = 443
        env = env_cls.return_value
        env.get_env_value.side_effect = lambda key, default="": {
            "DOMAIN": "",
            "SSL_CERT": "",
            "BEHIND_NGINX": "0",
            "USE_HTTPS": "0",
            "BACKEND_HOST": "0.0.0.0",
            "BACKEND_PORT": "8000",
            "HTTPS_PUBLIC_PORT": "443",
            "PUBLISH_MODE": "http_direct",
        }.get(key, default)
        bps.return_value = {
            "portal_ready": False,
            "portal_mode_supported": False,
            "portal_access_url": "",
        }
        assert portal.resolve_portal_base_url(db) is None


def test_resolve_portal_base_url_ignores_panel_access_path():
    """Portal host is always at /; panel ACCESS_PATH must not appear in portal links."""
    db = MagicMock()
    row = MagicMock()
    row.value = "portal.example.com"
    db.query.return_value.filter.return_value.first.return_value = row
    with (
        patch("app.services.client_portal.get_settings") as gs,
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.panel_publish_info.resolve_panel_publish_mode", return_value="behind_nginx"),
        patch("app.services.panel_publish_info.resolve_active_publish_mode_key", return_value="nginx_le"),
        patch("app.services.panel_publish_info.build_portal_publish_status") as bps,
    ):
        gs.return_value.https_public_port = 443
        gs.return_value.access_path = "/panel"
        gs.return_value.domain = "panel.example.com"
        env = env_cls.return_value
        env.get_env_value.side_effect = lambda key, default="": {
            "DOMAIN": "panel.example.com",
            "SSL_CERT": "/c.pem",
            "BEHIND_NGINX": "1",
            "USE_HTTPS": "1",
            "BACKEND_HOST": "127.0.0.1",
            "BACKEND_PORT": "8000",
            "HTTPS_PUBLIC_PORT": "443",
            "PUBLISH_MODE": "nginx_le",
        }.get(key, default)
        bps.return_value = {"portal_ready": True, "portal_access_url": "https://portal.example.com/"}
        assert portal.resolve_portal_base_url(db) == "https://portal.example.com"
        assert "/panel" not in (portal.resolve_portal_base_url(db) or "")


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
        revoked_at=_utc_now_naive(),
    )
    empty = MagicMock()
    empty.filter.return_value.first.return_value = None
    revoked = MagicMock()
    revoked.filter.return_value.first.return_value = row
    db.query.side_effect = [revoked, empty]
    with pytest.raises(HTTPException) as ei:
        portal.get_valid_portal_token(db, "abc")
    assert ei.value.status_code == 410


def test_get_valid_portal_token_resolves_user_token():
    db = MagicMock()
    row = UserPortalToken(id=2, token="usr", user_id=7, revoked_at=None)
    empty = MagicMock()
    empty.filter.return_value.first.return_value = None
    active = MagicMock()
    active.filter.return_value.first.return_value = row
    db.query.side_effect = [empty, active]
    resolved = portal.get_valid_portal_token(db, "usr")
    assert resolved.kind == "user"
    assert resolved.user_row is row


def test_new_token_value_retries_when_value_exists_in_other_portal_table():
    with (
        patch("app.services.client_portal.secrets.token_urlsafe", side_effect=["dup", "fresh"]),
        patch("app.services.client_portal._token_exists", side_effect=[True, False]),
    ):
        assert portal._new_token_value(MagicMock(), prefix="c_") == "c_fresh"


def test_create_paths_namespace_tokens_across_tables():
    client_db = MagicMock()
    user_db = MagicMock()
    configs = [VpnConfig(node_id=1, client_name="alice")]
    with (
        patch("app.services.client_portal.ensure_client_configs", return_value=configs),
        patch("app.services.client_portal.ensure_portal_user"),
        patch("app.services.client_portal._active_token", return_value=None),
        patch("app.services.client_portal._active_user_token", return_value=None),
        patch("app.services.client_portal.secrets.token_urlsafe", side_effect=["shared", "shared"]),
        patch("app.services.client_portal._token_exists", return_value=False),
    ):
        client_row = portal.get_or_create_portal_token(client_db, client_name="alice")
        user_row = portal.get_or_create_user_portal_token(user_db, user_id=7)

    assert client_row.token == "c_shared"
    assert user_row.token == "u_shared"
    assert client_row.token != user_row.token


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
    with (
        patch("app.services.client_portal.get_settings") as gs,
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.panel_publish_info.resolve_panel_publish_mode", return_value="behind_nginx"),
        patch("app.services.panel_publish_info.resolve_active_publish_mode_key", return_value="nginx_le"),
        patch("app.services.panel_publish_info.build_portal_publish_status") as bps,
    ):
        gs.return_value.https_public_port = 443
        gs.return_value.access_path = ""
        gs.return_value.domain = "panel.example.com"
        env = env_cls.return_value
        env.get_env_value.side_effect = lambda key, default="": {
            "DOMAIN": "panel.example.com",
            "SSL_CERT": "/c.pem",
            "BEHIND_NGINX": "1",
            "USE_HTTPS": "1",
            "BACKEND_HOST": "127.0.0.1",
            "BACKEND_PORT": "8000",
            "HTTPS_PUBLIC_PORT": "443",
            "PUBLISH_MODE": "nginx_le",
        }.get(key, default)
        bps.return_value = {"portal_ready": True, "portal_access_url": "https://sub.example.com/"}
        payload = portal.link_response(db, token)
    assert payload["url"] == "https://sub.example.com/p/XxYy"
    assert payload["token"] == "XxYy"


def test_format_bytes_label():
    assert portal._format_bytes_label(0) == "0 B"
    assert "GiB" in portal._format_bytes_label(44.69 * 1024**3)


def test_build_portal_status_active_unlimited():
    db = MagicMock()
    # OpenVPN policy: not blocked, no limit
    policy = MagicMock()
    policy.is_permanent_blocked = False
    policy.is_temp_blocked = False
    policy.block_until = None
    policy.traffic_limit_bytes = None
    policy.expires_at = None
    # traffic stats
    stat = MagicMock()
    stat.total_received = 1024
    stat.total_sent = 2048

    def query_side_effect(model):
        q = MagicMock()
        if model.__name__ == "OpenVpnAccessPolicy":
            q.filter.return_value.first.return_value = policy
        elif model.__name__ == "UserTrafficStatProtocol":
            q.filter.return_value.all.return_value = [stat]
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    db.query.side_effect = query_side_effect
    cfg = MagicMock()
    cfg.vpn_type = VpnType.openvpn
    cfg.expires_at = None
    cfg.cert_expires_at = None
    status = portal.build_portal_status(db, node_id=1, client_name="alice", configs=[cfg])
    assert status["status"] == "active"
    assert status["expires_label"] == "Бессрочно"
    assert status["traffic_used_bytes"] == 3072
    assert status["traffic_limit_bytes"] is None
    assert "/ ∞" in status["traffic_label"]


def test_build_portal_status_uses_cert_expires_at():
    db = MagicMock()

    def query_side_effect(model):
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        q.filter.return_value.all.return_value = []
        return q

    db.query.side_effect = query_side_effect
    now = _utc_now_naive()
    cfg = MagicMock()
    cfg.vpn_type = VpnType.openvpn
    cfg.expires_at = None
    cfg.cert_expires_at = now + __import__("datetime").timedelta(days=25, hours=2)
    status = portal.build_portal_status(db, node_id=1, client_name="test1", configs=[cfg])
    assert status["status"] == "active"
    assert status["expires_label"].startswith("25 дн. (до ")
    assert status["expires_at"] is not None


def test_build_portal_status_prefers_access_until_over_cert():
    db = MagicMock()
    now = _utc_now_naive()

    policy = MagicMock()
    policy.is_permanent_blocked = False
    policy.is_temp_blocked = False
    policy.block_until = None
    policy.traffic_limit_bytes = None
    policy.access_until = now + timedelta(days=40, hours=2)

    def query_side_effect(model):
        q = MagicMock()
        if model.__name__ == "OpenVpnAccessPolicy":
            q.filter.return_value.first.return_value = policy
        elif model.__name__ == "UserTrafficStatProtocol":
            q.filter.return_value.all.return_value = []
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    db.query.side_effect = query_side_effect
    cfg = MagicMock()
    cfg.vpn_type = VpnType.openvpn
    cfg.expires_at = None
    cfg.cert_expires_at = now + timedelta(days=5)
    status = portal.build_portal_status(db, node_id=1, client_name="test1", configs=[cfg])
    assert status["status"] == "active"
    assert status["expires_label"].startswith("40 дн. (до ")
    assert status["expires_at"] == (policy.access_until.isoformat() + "Z")


def test_build_portal_status_marks_access_until_expired_even_if_cert_valid():
    db = MagicMock()
    now = _utc_now_naive()

    policy = MagicMock()
    policy.is_permanent_blocked = False
    policy.is_temp_blocked = False
    policy.block_until = None
    policy.traffic_limit_bytes = None
    policy.access_until = now - timedelta(days=1)

    def query_side_effect(model):
        q = MagicMock()
        if model.__name__ == "OpenVpnAccessPolicy":
            q.filter.return_value.first.return_value = policy
        elif model.__name__ == "UserTrafficStatProtocol":
            q.filter.return_value.all.return_value = []
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    db.query.side_effect = query_side_effect
    cfg = MagicMock()
    cfg.vpn_type = VpnType.openvpn
    cfg.expires_at = None
    cfg.cert_expires_at = now + timedelta(days=25)
    status = portal.build_portal_status(db, node_id=1, client_name="test1", configs=[cfg])
    assert status["status"] == "expired"
    assert status["expires_label"].startswith("истёк ")
    assert status["expires_at"] == (policy.access_until.isoformat() + "Z")


def test_public_portal_redeem_returns_access_until(public_client):
    token_row = ClientPortalToken(id=1, token="tok", node_id=1, client_name="alice", revoked_at=None)
    fixed_until = datetime(2030, 1, 8, 12, 30)
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service") as rl,
        patch("app.routers.public_portal.get_valid_portal_token", return_value=token_row),
        patch(
            "app.routers.public_portal.redeem_public_portal_code",
            return_value={
                "grant_days": 7,
                "protocols_applied": ["openvpn"],
                "access_until_by_protocol": {"openvpn": fixed_until.isoformat()},
                "access_until": fixed_until.isoformat(),
            },
        ),
    ):
        feats.return_value.is_enabled.side_effect = lambda key: True
        ip_svc.get_client_ip.return_value = "198.51.100.1"
        resp = public_client.post(
            "/api/public/portal/tok/redeem",
            json={"code": "ABCD-EFGH-IJKL"},
            headers={"Host": "sub.example.com"},
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": True,
        "grant_days": 7,
        "protocols_applied": ["openvpn"],
        "access_until": fixed_until.isoformat(),
        "access_until_by_protocol": {"openvpn": fixed_until.isoformat()},
    }
    rl.consume.assert_called_once_with("198.51.100.1")


def test_public_portal_redeem_returns_bad_request_for_redeem_errors(public_client):
    token_row = ClientPortalToken(id=1, token="tok", node_id=1, client_name="alice", revoked_at=None)
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service") as rl,
        patch("app.routers.public_portal.get_valid_portal_token", return_value=token_row),
        patch(
            "app.routers.public_portal.redeem_public_portal_code",
            side_effect=ValueError("Этот unlock-ключ уже использован вами"),
        ),
    ):
        feats.return_value.is_enabled.side_effect = lambda key: True
        ip_svc.get_client_ip.return_value = "198.51.100.1"
        resp = public_client.post(
            "/api/public/portal/tok/redeem",
            json={"code": "ABCD-EFGH-IJKL"},
            headers={"Host": "sub.example.com"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Этот unlock-ключ уже использован вами"
    rl.consume.assert_called_once_with("198.51.100.1")


def test_public_portal_redeem_requires_unlock_codes_feature(public_client):
    token_row = ClientPortalToken(id=1, token="tok", node_id=1, client_name="alice", revoked_at=None)
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service"),
        patch("app.routers.public_portal.get_valid_portal_token", return_value=token_row),
    ):
        feats.return_value.is_enabled.side_effect = lambda key: key == "client_portal"
        ip_svc.get_client_ip.return_value = "198.51.100.1"
        resp = public_client.post(
            "/api/public/portal/tok/redeem",
            json={"code": "ABCD-EFGH-IJKL"},
            headers={"Host": "sub.example.com"},
        )

    assert resp.status_code == 403
    assert "unlock" in resp.json()["detail"].lower()


def test_public_portal_redeem_rejects_wrong_host_before_features(public_client):
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host", side_effect=HTTPException(status_code=404, detail="Not found")),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service") as rl,
    ):
        resp = public_client.post(
            "/api/public/portal/tok/redeem",
            json={"code": "ABCD-EFGH-IJKL"},
            headers={"Host": "wrong.example.com"},
        )

    assert resp.status_code == 404
    feats.assert_not_called()
    ip_svc.get_client_ip.assert_not_called()
    rl.consume.assert_not_called()


def test_public_portal_redeem_rate_limit_propagates(public_client):
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service") as rl,
        patch("app.routers.public_portal.get_valid_portal_token") as get_token,
        patch("app.routers.public_portal.redeem_public_portal_code") as redeem,
    ):
        ip_svc.get_client_ip.return_value = "198.51.100.9"
        rl.consume.side_effect = HTTPException(status_code=429, detail="too many")
        resp = public_client.post(
            "/api/public/portal/tok/redeem",
            json={"code": "ABCD-EFGH-IJKL"},
            headers={"Host": "sub.example.com"},
        )

    assert resp.status_code == 429
    assert resp.json()["detail"] == "too many"
    feats.assert_not_called()
    get_token.assert_not_called()
    redeem.assert_not_called()


def test_public_download_passes_user_target_query_params(public_client):
    user_token = UserPortalToken(id=1, token="tok", user_id=10, revoked_at=None)
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service") as rl,
        patch("app.routers.public_portal.get_valid_portal_token", return_value=user_token),
        patch("app.routers.public_portal.read_portal_profile", return_value=("bob.ovpn", b"client\n")) as read_profile,
    ):
        feats.return_value.is_enabled.return_value = True
        ip_svc.get_client_ip.return_value = "198.51.100.1"
        resp = public_client.get(
            "/api/public/portal/tok/download",
            params={"path": "/tmp/bob.ovpn", "node_id": 2, "client_name": "bob"},
            headers={"Host": "sub.example.com"},
        )

    assert resp.status_code == 200
    read_profile.assert_called_once_with(
        ANY,
        user_token,
        "/tmp/bob.ovpn",
        node_id=2,
        client_name="bob",
    )
    rl.consume.assert_called_once_with("198.51.100.1")


def test_build_user_portal_payload_lists_clients_and_marks_expired_subscription():
    db = MagicMock()
    expired_user = MagicMock(id=7, access_until=_utc_now_naive() - timedelta(days=1))
    alice_entry = {
        "node_id": 1,
        "client_name": "alice",
        "protocols": ["openvpn"],
        "files": [],
        "status": {
            "status": "active",
            "status_label": "Активна",
            "expires_at": None,
            "expires_label": "Бессрочно",
            "traffic_used_bytes": 0,
            "traffic_limit_bytes": None,
            "traffic_label": "0 B / ∞",
        },
    }
    bob_entry = {
        "node_id": 2,
        "client_name": "bob",
        "protocols": ["wireguard"],
        "files": [],
        "status": {
            "status": "blocked",
            "status_label": "Заблокирована",
            "expires_at": None,
            "expires_label": "Бессрочно",
            "traffic_used_bytes": 0,
            "traffic_limit_bytes": None,
            "traffic_label": "0 B / ∞",
        },
    }
    with (
        patch("app.services.client_portal.resolve_portal_base_url", return_value="https://sub.example.com"),
        patch("app.services.client_portal.ensure_portal_user", return_value=expired_user),
        patch("app.services.client_portal._owned_portal_targets", return_value=[(1, "alice"), (2, "bob")]),
        patch("app.services.client_portal._build_client_portal_entry", side_effect=[alice_entry, bob_entry]),
        patch("app.services.feature_guards.get_feature_service") as feats,
    ):
        feats.return_value.is_enabled.side_effect = lambda key: key == "unlock_codes"
        payload = portal.build_user_portal_payload(
            db,
            UserPortalToken(id=3, token="usr", user_id=7, revoked_at=None),
        )

    assert payload["kind"] == "user"
    assert payload["user_id"] == 7
    assert len(payload["clients"]) == 2
    assert payload["clients"][0]["client_name"] == "alice"
    assert payload["clients"][0]["status"]["status"] == "expired"
    assert payload["clients"][0]["status"]["status_label"] == "Истекла"
    assert payload["clients"][1]["status"]["status"] == "blocked"


def test_redeem_public_portal_code_user_retries_next_owned_client():
    user_token = UserPortalToken(id=3, token="usr", user_id=7, revoked_at=None)
    fixed_until = datetime(2030, 1, 8, 12, 30)
    user = MagicMock(id=7, access_until=fixed_until)
    with (
        patch("app.services.client_portal._owned_portal_targets", return_value=[(1, "alice"), (2, "bob")]),
        patch("app.services.client_portal.ensure_portal_user", return_value=user),
        patch("app.services.unlock_codes.redeem_unlock_code") as redeem,
    ):
        redeem.side_effect = [
            ValueError("Нет пересечения протоколов клиента и unlock-ключа"),
            {
                "grant_days": 7,
                "protocols_applied": ["openvpn"],
                "access_until_by_protocol": {"openvpn": fixed_until.isoformat()},
            },
        ]
        result = portal.redeem_public_portal_code(
            MagicMock(),
            portal.PortalTokenResolution(kind="user", user_row=user_token),
            code="ABCD-EFGH-IJKL",
        )

    assert redeem.call_count == 2
    assert [call.kwargs["user_id"] for call in redeem.call_args_list] == [7, 7]
    assert result["access_until"] == fixed_until.isoformat()
    assert result["protocols_applied"] == ["openvpn"]


def test_redeem_public_portal_code_user_skips_manually_blocked_client():
    user_token = UserPortalToken(id=3, token="usr", user_id=7, revoked_at=None)
    fixed_until = datetime(2030, 1, 8, 12, 30)
    user = MagicMock(id=7, access_until=fixed_until)
    with (
        patch("app.services.client_portal._owned_portal_targets", return_value=[(1, "alice"), (2, "bob")]),
        patch("app.services.client_portal.ensure_portal_user", return_value=user),
        patch("app.services.unlock_codes.redeem_unlock_code") as redeem,
    ):
        redeem.side_effect = [
            ValueError(unlock_codes._REDEEM_MANUAL_BLOCK_MESSAGE),
            {
                "grant_days": 7,
                "protocols_applied": ["wireguard"],
                "access_until_by_protocol": {"wireguard": fixed_until.isoformat()},
            },
        ]
        result = portal.redeem_public_portal_code(
            MagicMock(),
            portal.PortalTokenResolution(kind="user", user_row=user_token),
            code="ABCD-EFGH-IJKL",
        )

    assert redeem.call_count == 2
    assert result["protocols_applied"] == ["wireguard"]


def test_redeem_public_portal_code_user_reports_manual_block_when_no_profile_left():
    user_token = UserPortalToken(id=3, token="usr", user_id=7, revoked_at=None)
    with (
        patch("app.services.client_portal._owned_portal_targets", return_value=[(1, "alice")]),
        patch("app.services.unlock_codes.redeem_unlock_code") as redeem,
    ):
        redeem.side_effect = ValueError(unlock_codes._REDEEM_MANUAL_BLOCK_MESSAGE)
        with pytest.raises(ValueError) as excinfo:
            portal.redeem_public_portal_code(
                MagicMock(),
                portal.PortalTokenResolution(kind="user", user_row=user_token),
                code="ABCD-EFGH-IJKL",
            )

    assert str(excinfo.value) == unlock_codes._REDEEM_MANUAL_BLOCK_MESSAGE


def test_admin_user_portal_get_link_route_uses_user_id():
    app = FastAPI()
    app.include_router(client_portal_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[require_admin] = lambda: MagicMock(id=1, username="admin")

    with (
        patch("app.routers.client_portal.get_feature_service") as feats,
        patch("app.routers.client_portal._require_portal_domain"),
        patch("app.routers.client_portal.ensure_portal_user"),
        patch(
            "app.routers.client_portal.get_or_create_user_portal_token",
            return_value=UserPortalToken(id=1, token="usr", user_id=9, revoked_at=None),
        ) as create_link,
        patch(
            "app.routers.client_portal.user_link_response",
            return_value={"kind": "user", "token": "usr", "user_id": 9, "url": "https://sub.example.com/p/usr", "revoked": False},
        ),
    ):
        feats.return_value.is_enabled.return_value = True
        with TestClient(app) as client:
            resp = client.get("/api/portal/users/9/link")

    assert resp.status_code == 200
    assert resp.json()["user_id"] == 9
    assert create_link.call_args.kwargs["user_id"] == 9


def test_admin_user_portal_revoke_route_uses_user_id():
    app = FastAPI()
    app.include_router(client_portal_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[require_admin] = lambda: MagicMock(id=1, username="admin")

    with (
        patch("app.routers.client_portal.get_feature_service") as feats,
        patch("app.routers.client_portal.ensure_portal_user"),
        patch("app.routers.client_portal.revoke_user_portal_token") as revoke_link,
    ):
        feats.return_value.is_enabled.return_value = True
        with TestClient(app) as client:
            resp = client.post("/api/portal/users/9/revoke")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "user_id": 9}
    assert revoke_link.call_args.kwargs["user_id"] == 9


def test_portal_protocol_prefers_file_protocol_over_db_vpn_type():
    cfg = MagicMock()
    cfg.vpn_type = VpnType.wireguard
    assert portal._portal_protocol_for_file({"protocol": "amneziawg"}, cfg) == "amneziawg"
    assert portal._portal_protocol_for_file({"protocol": "wireguard"}, cfg) == "wireguard"
    assert portal._portal_protocol_for_file({}, cfg) == "wireguard"


_AZ_ONLY_POLICY = {
    "routes": ["az"],
    "protocols": ["openvpn", "wireguard", "amneziawg", "amneziawg2"],
    "openvpn_groups": ["udp_tcp", "udp", "tcp"],
}

_AZ_TOPTINKER_PATH = "/client/openvpn/antizapret/AZ-TopTinker.ovpn"
_VPN_TOPTINKER_PATH = "/client/openvpn/vpn/VPN-TopTinker.ovpn"


def _toptinker_openvpn_files() -> list[dict]:
    return [
        {
            "protocol": "openvpn",
            "variant": "antizapret",
            "path": _AZ_TOPTINKER_PATH,
            "filename": "AZ-TopTinker.ovpn",
        },
        {
            "protocol": "openvpn",
            "variant": "vpn",
            "path": _VPN_TOPTINKER_PATH,
            "filename": "VPN-TopTinker.ovpn",
        },
    ]


def _toptinker_cfg(*, owner_id: int | None) -> MagicMock:
    cfg = MagicMock()
    cfg.id = 7
    cfg.node_id = 3
    cfg.client_name = "TopTinker"
    cfg.vpn_type = VpnType.openvpn
    cfg.owner_id = owner_id
    return cfg


def _portal_db_for_list_and_download(*, configs: list, node: MagicMock, owner=None):
    """MagicMock db: VpnConfig → configs; Node → node; User via db.get."""
    db = MagicMock()

    def query_side_effect(model):
        q = MagicMock()
        name = getattr(model, "__name__", "")
        if name == "VpnConfig" or model is VpnConfig:
            q.filter.return_value.all.return_value = configs
            return q
        if name == "Node" or model is type(node):
            q.filter.return_value.first.return_value = node
            return q
        q.filter.return_value.first.return_value = owner
        q.filter.return_value.all.return_value = []
        return q

    db.query.side_effect = query_side_effect
    if owner is not None:
        db.get.side_effect = lambda model, pk: owner if pk == getattr(owner, "id", None) else None
    else:
        db.get.return_value = None
    return db


def test_list_files_hides_vpn_route_when_owner_visibility_az_only():
    from app.models import User, UserRole
    from app.services.vpn_profile_visibility import policy_to_json

    owner = User(
        id=5,
        username="novikov",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        visible_vpn_profiles=policy_to_json(_AZ_ONLY_POLICY),
    )
    cfg = _toptinker_cfg(owner_id=5)
    adapter = MagicMock()
    adapter.get_profile_files.return_value = _toptinker_openvpn_files()
    node = MagicMock()
    db = _portal_db_for_list_and_download(configs=[cfg], node=node, owner=owner)

    with (
        patch("app.services.client_portal.get_adapter_for_node", return_value=adapter),
        patch("app.services.feature_guards.get_feature_service") as feats,
    ):
        feats.return_value.is_enabled.return_value = True
        files = portal._list_files_for_configs(db, [cfg])

    paths = [f["path"] for f in files]
    assert _AZ_TOPTINKER_PATH in paths
    assert _VPN_TOPTINKER_PATH not in paths


def test_list_files_orphan_uses_restrictive_default_visibility():
    cfg = _toptinker_cfg(owner_id=None)
    adapter = MagicMock()
    adapter.get_profile_files.return_value = _toptinker_openvpn_files()
    node = MagicMock()
    db = _portal_db_for_list_and_download(configs=[cfg], node=node, owner=None)

    with (
        patch("app.services.client_portal.get_adapter_for_node", return_value=adapter),
        patch("app.services.feature_guards.get_feature_service") as feats,
        patch("app.services.client_portal.get_default_visible_vpn_profiles", return_value=_AZ_ONLY_POLICY),
        patch(
            "app.services.client_portal.feature_flags_from_service",
            return_value={"openvpn": True, "wireguard": True, "amneziawg": True, "awg2": True},
        ),
    ):
        feats.return_value.is_enabled.return_value = True
        files = portal._list_files_for_configs(db, [cfg])

    paths = [f["path"] for f in files]
    assert _AZ_TOPTINKER_PATH in paths
    assert _VPN_TOPTINKER_PATH not in paths


def test_read_client_portal_profile_rejects_vpn_via_owner_visibility():
    """Download allowlist comes from real _list_files_for_configs (no stub)."""
    from app.models import User, UserRole
    from app.services.vpn_profile_visibility import policy_to_json

    owner = User(
        id=5,
        username="novikov",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        visible_vpn_profiles=policy_to_json(_AZ_ONLY_POLICY),
    )
    cfg = _toptinker_cfg(owner_id=5)
    adapter = MagicMock()
    adapter.get_profile_files.return_value = _toptinker_openvpn_files()
    node = MagicMock()
    db = _portal_db_for_list_and_download(configs=[cfg], node=node, owner=owner)

    with (
        patch("app.services.client_portal.get_adapter_for_node", return_value=adapter),
        patch("app.services.feature_guards.get_feature_service") as feats,
        patch("app.services.client_portal.load_node_remote_hosts", return_value=[]),
        patch(
            "app.services.client_portal.read_profile_file_for_delivery",
            return_value=b"client\n",
        ) as read_file,
    ):
        feats.return_value.is_enabled.return_value = True
        with pytest.raises(HTTPException) as hidden:
            portal._read_client_portal_profile(
                db,
                node_id=3,
                client_name="TopTinker",
                path=_VPN_TOPTINKER_PATH,
            )
        assert hidden.value.status_code == 404
        read_file.assert_not_called()

        filename, content = portal._read_client_portal_profile(
            db,
            node_id=3,
            client_name="TopTinker",
            path=_AZ_TOPTINKER_PATH,
        )
    assert content == b"client\n"
    assert "AZ" in filename or filename.endswith(".ovpn")


def test_read_client_portal_profile_rejects_vpn_for_orphan_default_az_only():
    cfg = _toptinker_cfg(owner_id=None)
    adapter = MagicMock()
    adapter.get_profile_files.return_value = _toptinker_openvpn_files()
    node = MagicMock()
    db = _portal_db_for_list_and_download(configs=[cfg], node=node, owner=None)

    with (
        patch("app.services.client_portal.get_adapter_for_node", return_value=adapter),
        patch("app.services.feature_guards.get_feature_service") as feats,
        patch("app.services.client_portal.get_default_visible_vpn_profiles", return_value=_AZ_ONLY_POLICY),
        patch(
            "app.services.client_portal.feature_flags_from_service",
            return_value={"openvpn": True, "wireguard": True, "amneziawg": True, "awg2": True},
        ),
    ):
        feats.return_value.is_enabled.return_value = True
        with pytest.raises(HTTPException) as hidden:
            portal._read_client_portal_profile(
                db,
                node_id=3,
                client_name="TopTinker",
                path=_VPN_TOPTINKER_PATH,
            )
    assert hidden.value.status_code == 404


def test_build_user_portal_payload_hides_vpn_for_restricted_owner():
    from app.models import User, UserRole
    from app.services.vpn_profile_visibility import policy_to_json

    owner = User(
        id=5,
        username="novikov",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        visible_vpn_profiles=policy_to_json(_AZ_ONLY_POLICY),
    )
    cfg = _toptinker_cfg(owner_id=5)
    adapter = MagicMock()
    adapter.get_profile_files.return_value = _toptinker_openvpn_files()
    node = MagicMock()
    db = _portal_db_for_list_and_download(configs=[cfg], node=node, owner=owner)
    token_row = MagicMock(token="u_tok", user_id=5)

    with (
        patch("app.services.client_portal.resolve_portal_base_url", return_value="https://portal.example.com"),
        patch("app.services.client_portal.ensure_portal_user", return_value=owner),
        patch("app.services.client_portal._owned_portal_targets", return_value=[(3, "TopTinker")]),
        patch("app.services.client_portal.get_adapter_for_node", return_value=adapter),
        patch("app.services.client_portal.build_portal_status", return_value={"state": "active"}),
        patch("app.services.client_portal._apply_user_subscription_status", side_effect=lambda status, _u: status),
        patch("app.services.client_portal._portal_brand_title", return_value="VPN"),
        patch("app.services.feature_guards.get_feature_service") as feats,
    ):
        feats.return_value.is_enabled.return_value = True
        payload = portal.build_user_portal_payload(db, token_row)

    assert payload["kind"] == "user"
    assert len(payload["clients"]) == 1
    paths = [f["path"] for f in payload["clients"][0]["files"]]
    assert _AZ_TOPTINKER_PATH in paths
    assert _VPN_TOPTINKER_PATH not in paths


def test_list_files_hides_wireguard_when_feature_disabled():
    db = MagicMock()
    cfg = MagicMock()
    cfg.id = 7
    cfg.node_id = 3
    cfg.client_name = "test1"
    cfg.vpn_type = VpnType.wireguard
    cfg.owner_id = None
    adapter = MagicMock()
    adapter.get_profile_files.return_value = [
        {"protocol": "wireguard", "variant": "vpn", "path": "/client/wireguard/vpn/a-wg.conf", "filename": "a-wg.conf"},
        {"protocol": "amneziawg", "variant": "vpn", "path": "/client/amneziawg/vpn/a-am.conf", "filename": "a-am.conf"},
    ]
    node = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = node

    def feat_enabled(key: str) -> bool:
        return key != "wireguard"

    with (
        patch("app.services.client_portal.get_adapter_for_node", return_value=adapter) as get_adapter,
        patch("app.services.feature_guards.get_feature_service") as feats,
        patch(
            "app.services.client_portal.get_default_visible_vpn_profiles",
            return_value={
                "routes": ["az", "vpn"],
                "protocols": ["openvpn", "wireguard", "amneziawg", "amneziawg2"],
                "openvpn_groups": ["udp_tcp", "udp", "tcp"],
            },
        ),
    ):
        feats.return_value.is_enabled.side_effect = feat_enabled
        files = portal._list_files_for_configs(db, [cfg])

    get_adapter.assert_called_once_with(node)
    assert [f["vpn_type"] for f in files] == ["amneziawg"]
    assert files[0]["filename"].startswith("AWG-")


def test_collect_access_policies_lowercases_wg_client_name():
    from app.models import AmneziaWg2AccessPolicy, WgAccessPolicy

    db = MagicMock()
    filter_calls: list[tuple[str, tuple]] = []

    def make_query(model):
        q = MagicMock()

        def filter_(*args, **kwargs):
            filter_calls.append((model.__name__, args))
            return q

        q.filter.side_effect = filter_
        q.first.return_value = None
        return q

    db.query.side_effect = make_query
    portal._collect_access_policies(
        db,
        node_id=1,
        client_name="Alice",
        protocols={"wireguard", "amneziawg2"},
    )

    names: list[tuple[str, str]] = []
    for model_name, args in filter_calls:
        for expr in args:
            right = getattr(expr, "right", None)
            value = getattr(right, "value", None)
            if isinstance(value, str):
                names.append((model_name, value))
    assert ("WgAccessPolicy", "alice") in names
    assert ("AmneziaWg2AccessPolicy", "alice") in names
    assert WgAccessPolicy.__name__ in {m for m, _ in filter_calls}
    assert AmneziaWg2AccessPolicy.__name__ in {m for m, _ in filter_calls}
