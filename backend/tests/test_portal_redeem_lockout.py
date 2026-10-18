"""B8: portal redeem lockout — 5 failures / 10 min per portal token."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.models import ClientPortalToken
from app.routers import public_portal as public_portal_router
from app.services.portal_redeem_lockout import PortalRedeemLockoutService


@pytest.fixture
def public_client():
    app = FastAPI()
    app.include_router(public_portal_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fresh_lockout(monkeypatch):
    svc = PortalRedeemLockoutService()
    monkeypatch.setattr(public_portal_router, "portal_redeem_lockout_service", svc)
    monkeypatch.setattr(
        "app.services.portal_redeem_lockout.portal_redeem_lockout_service",
        svc,
    )
    return svc


def _post_redeem(client, *, token: str = "portal-tok-a", code: str = "BAD-CODE"):
    return client.post(
        f"/api/public/portal/{token}/redeem",
        json={"code": code},
        headers={"Host": "sub.example.com"},
    )


def test_portal_redeem_lockout_after_five_failures(public_client):
    token_row = ClientPortalToken(id=1, token="portal-tok-a", node_id=1, client_name="alice", revoked_at=None)
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service"),
        patch("app.routers.public_portal.get_valid_portal_token", return_value=token_row),
        patch(
            "app.routers.public_portal.redeem_public_portal_code",
            side_effect=ValueError("Неверный unlock-ключ"),
        ) as redeem,
    ):
        feats.return_value.is_enabled.side_effect = lambda key: True
        ip_svc.get_client_ip.return_value = "198.51.100.1"

        for _ in range(5):
            resp = _post_redeem(public_client)
            assert resp.status_code == 400
            assert resp.json()["detail"] == "Неверный unlock-ключ"

        locked = _post_redeem(public_client)
        assert locked.status_code == 429
        assert "попыт" in locked.json()["detail"].lower()
        assert redeem.call_count == 5


def test_portal_redeem_lockout_is_per_token(public_client):
    row_a = ClientPortalToken(id=1, token="tok-a", node_id=1, client_name="alice", revoked_at=None)
    row_b = ClientPortalToken(id=2, token="tok-b", node_id=1, client_name="bob", revoked_at=None)

    def _token(_db, token: str):
        return row_a if token == "tok-a" else row_b

    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service"),
        patch("app.routers.public_portal.get_valid_portal_token", side_effect=_token),
        patch(
            "app.routers.public_portal.redeem_public_portal_code",
            side_effect=ValueError("Неверный unlock-ключ"),
        ),
    ):
        feats.return_value.is_enabled.side_effect = lambda key: True
        ip_svc.get_client_ip.return_value = "198.51.100.1"

        for _ in range(5):
            assert _post_redeem(public_client, token="tok-a").status_code == 400

        assert _post_redeem(public_client, token="tok-a").status_code == 429
        assert _post_redeem(public_client, token="tok-b").status_code == 400


def test_portal_redeem_lockout_does_not_bypass_unlock_codes_guard(public_client):
    with (
        patch("app.routers.public_portal.get_feature_service") as feats,
        patch("app.routers.public_portal.assert_portal_host"),
        patch("app.routers.public_portal.ip_restriction_service") as ip_svc,
        patch("app.routers.public_portal.public_download_rate_limit_service"),
        patch("app.routers.public_portal.get_valid_portal_token") as get_token,
        patch("app.routers.public_portal.redeem_public_portal_code") as redeem,
    ):
        feats.return_value.is_enabled.side_effect = lambda key: key == "client_portal"
        ip_svc.get_client_ip.return_value = "198.51.100.1"
        resp = _post_redeem(public_client)

    assert resp.status_code == 403
    get_token.assert_not_called()
    redeem.assert_not_called()
