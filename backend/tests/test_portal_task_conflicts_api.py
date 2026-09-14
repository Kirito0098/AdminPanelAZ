from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import require_admin
from app.database import get_db
from app.routers import security as security_router
from app.routers import settings_vpn_network as vpn_router


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(security_router.router, prefix="/api")
    app.include_router(vpn_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[require_admin] = lambda: MagicMock(id=1, username="admin")
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize(
    "active_task_type, expected_detail",
    [
        ("portal_readiness_check", "Проверка готовности портала уже выполняется"),
        ("portal_readiness_prepare", "Подготовка портала уже выполняется"),
    ],
)
def test_portal_publish_409_when_readiness_active(api_client, active_task_type, expected_detail):
    def _find_active_task(task_type: str):
        if task_type == active_task_type:
            return MagicMock(id=123)
        return None

    with (
        patch("app.services.feature_guards.get_feature_service") as feats,
        patch("app.services.client_portal.normalize_portal_domain", return_value="portal.example.com"),
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.panel_publish_info.resolve_panel_publish_mode", return_value="behind_nginx"),
        patch("app.services.panel_publish_info.resolve_active_publish_mode_key", return_value="nginx_le"),
        patch("app.services.background_tasks.background_task_service.find_active_task", side_effect=_find_active_task),
    ):
        feats.return_value.is_enabled.return_value = True
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

        resp = api_client.post(
            "/api/security/portal-publish",
            json={"portal_domain": "portal.example.com", "save_domain": False},
        )

    assert resp.status_code == 409
    assert resp.json()["detail"] == expected_detail
    assert resp.json()["active_task_id"] == 123


def test_vpn_network_publish_409_when_portal_publish_active(api_client):
    def _find_active_task(task_type: str):
        if task_type == "portal_publish":
            return MagicMock(id=777)
        return None

    with (
        patch("app.routers.settings_vpn_network.get_feature_service") as feats,
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.background_tasks.background_task_service.find_active_task", side_effect=_find_active_task),
    ):
        feats.return_value.is_enabled.return_value = True
        env = env_cls.return_value
        env.get_env_value.side_effect = lambda key, default="": {
            "DOMAIN": "panel.example.com",
            "SSL_CERT": "",
            "SSL_KEY": "",
        }.get(key, default)

        resp = api_client.post("/api/settings/vpn-network/publish", json={"mode": "http_direct"})

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Сейчас выполняется настройка портала"
    assert resp.json()["active_task_id"] == 777


@pytest.mark.parametrize(
    "active_task_type, expected_detail",
    [
        ("portal_readiness_check", "Проверка готовности портала уже выполняется"),
        ("portal_readiness_prepare", "Подготовка портала уже выполняется"),
    ],
)
def test_vpn_network_publish_409_when_readiness_active(api_client, active_task_type, expected_detail):
    def _find_active_task(task_type: str):
        if task_type == active_task_type:
            return MagicMock(id=555)
        return None

    with (
        patch("app.routers.settings_vpn_network.get_feature_service") as feats,
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.background_tasks.background_task_service.find_active_task", side_effect=_find_active_task),
    ):
        feats.return_value.is_enabled.return_value = True
        env = env_cls.return_value
        env.get_env_value.side_effect = lambda key, default="": {
            "DOMAIN": "panel.example.com",
            "SSL_CERT": "",
            "SSL_KEY": "",
        }.get(key, default)

        resp = api_client.post("/api/settings/vpn-network/publish", json={"mode": "http_direct"})

    assert resp.status_code == 409
    assert resp.json()["detail"] == expected_detail
    assert resp.json()["active_task_id"] == 555


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/security/portal-readiness-check",
        "/api/security/portal-readiness-prepare",
    ],
)
def test_portal_readiness_409_when_vpn_publish_active(api_client, endpoint):
    def _find_active_task(task_type: str):
        if task_type == "vpn_network_publish":
            return MagicMock(id=888)
        return None

    with (
        patch("app.services.feature_guards.get_feature_service") as feats,
        patch("app.services.client_portal.normalize_portal_domain", return_value="portal.example.com"),
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.panel_publish_info.resolve_panel_publish_mode", return_value="behind_nginx"),
        patch("app.services.panel_publish_info.resolve_active_publish_mode_key", return_value="nginx_le"),
        patch("app.services.background_tasks.background_task_service.find_active_task", side_effect=_find_active_task),
    ):
        feats.return_value.is_enabled.return_value = True
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

        resp = api_client.post(
            endpoint,
            json={"portal_domain": "portal.example.com", "save_domain": False},
        )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Сначала дождитесь завершения публикации панели"
    assert resp.json()["active_task_id"] == 888


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/security/portal-publish",
        "/api/security/portal-readiness-check",
        "/api/security/portal-readiness-prepare",
    ],
)
@pytest.mark.parametrize("publish_mode", ["http_direct", "uvicorn_le", "uvicorn_selfsigned"])
def test_portal_actions_400_when_publish_mode_unsupported(api_client, endpoint, publish_mode):
    with (
        patch("app.services.feature_guards.get_feature_service") as feats,
        patch("app.services.client_portal.normalize_portal_domain", return_value="portal.example.com"),
        patch("app.services.client_portal.set_portal_domain") as set_domain,
        patch("app.services.env_file.EnvFileService") as env_cls,
        patch("app.services.panel_publish_info.resolve_panel_publish_mode", return_value="direct_http"),
        patch(
            "app.services.panel_publish_info.resolve_active_publish_mode_key",
            return_value=publish_mode,
        ),
        patch("app.services.background_tasks.background_task_service.find_active_task", return_value=None),
        patch("app.services.background_tasks.background_task_service.enqueue_background_task") as enqueue,
    ):
        feats.return_value.is_enabled.return_value = True
        env = env_cls.return_value
        env.get_env_value.side_effect = lambda key, default="": {
            "DOMAIN": "panel.example.com",
            "SSL_CERT": "",
            "BEHIND_NGINX": "0",
            "USE_HTTPS": "0",
            "BACKEND_HOST": "0.0.0.0",
            "BACKEND_PORT": "8000",
            "HTTPS_PUBLIC_PORT": "443",
            "PUBLISH_MODE": publish_mode,
        }.get(key, default)

        resp = api_client.post(
            endpoint,
            json={"portal_domain": "portal.example.com", "save_domain": True},
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Nginx" in detail
    assert "/settings/vpn_network" in detail
    set_domain.assert_not_called()
    enqueue.assert_not_called()

