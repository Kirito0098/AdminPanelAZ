"""Tests for OpenAPI /docs auth gate."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def test_openapi_docs_disabled_returns_404(api_test_env, monkeypatch):
    from app.config import Settings, get_settings

    env = api_test_env
    disabled = Settings(
        app_env="development",
        enforce_password_policy=False,
        auth_rate_limit_enabled=False,
        api_rate_limit_enabled=False,
        audit_log_enabled=False,
        security_headers_enabled=True,
        enforce_https=False,
        behind_nginx=False,
        openapi_docs_enabled=False,
    )
    monkeypatch.setattr("app.config.get_settings", lambda: disabled)
    monkeypatch.setattr("app.services.openapi_docs_gate.get_settings", lambda: disabled)
    get_settings.cache_clear()

    client = TestClient(env["app"])
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path)
        assert response.status_code == 404, path


def test_openapi_docs_admin_jwt(api_test_env):
    env = api_test_env
    client = TestClient(env["app"])
    headers = env["admin_headers"]

    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, path

    schema = client.get("/openapi.json", headers=headers).json()
    assert "openapi" in schema
    assert schema.get("info", {}).get("title")


def test_openapi_docs_allowed_ip(api_test_env, monkeypatch):
    from app.config import Settings, get_settings

    env = api_test_env
    gated = Settings(
        app_env="development",
        enforce_password_policy=False,
        auth_rate_limit_enabled=False,
        api_rate_limit_enabled=False,
        audit_log_enabled=False,
        security_headers_enabled=True,
        enforce_https=False,
        behind_nginx=False,
        openapi_docs_enabled=True,
        openapi_docs_allowed_ips="203.0.113.10",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: gated)
    monkeypatch.setattr("app.services.openapi_docs_gate.get_settings", lambda: gated)
    get_settings.cache_clear()

    client = TestClient(env["app"])
    denied = client.get("/docs")
    assert denied.status_code == 401

    with patch(
        "app.services.openapi_docs_gate.ip_restriction_service.get_client_ip",
        return_value="203.0.113.10",
    ):
        allowed = client.get("/openapi.json")
    assert allowed.status_code == 200


def test_openapi_docs_viewer_forbidden(api_test_env):
    env = api_test_env
    client = TestClient(env["app"])
    response = client.get("/docs", headers=env["viewer_headers"])
    assert response.status_code == 401
