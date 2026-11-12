"""Общие дефолты секретов и порта: проверка на старте и ротация используют одни константы."""

from __future__ import annotations

import pytest

from app.config import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_BACKEND_PORT,
    DEFAULT_NODE_AGENT_KEY,
    DEFAULT_SECRET_KEY,
    Settings,
)
from app.services import secrets_rotation as sr
from app.services.security_bootstrap import validate_node_agent_key, validate_panel_settings


def _definition(secret_id: str) -> sr.SecretDefinition:
    return sr.SecretDefinition(secret_id=secret_id, label="", description="", storage="env")


def test_production_rejects_default_secret_key() -> None:
    settings = Settings(app_env="production", secret_key=DEFAULT_SECRET_KEY)
    with pytest.raises(SystemExit):
        validate_panel_settings(settings)


def test_production_rejects_default_node_agent_key() -> None:
    with pytest.raises(SystemExit):
        validate_node_agent_key(DEFAULT_NODE_AGENT_KEY, production=True)


def test_production_rejects_default_admin_password() -> None:
    settings = Settings(
        app_env="production",
        secret_key="x" * 64,
        default_admin_password=DEFAULT_ADMIN_PASSWORD,
    )
    with pytest.raises(SystemExit):
        validate_panel_settings(settings)


def test_development_allows_default_admin_password() -> None:
    settings = Settings(app_env="development", default_admin_password=DEFAULT_ADMIN_PASSWORD)
    validate_panel_settings(settings)


def test_rotation_treats_the_same_defaults_as_unset() -> None:
    assert not sr._is_configured(_definition("secret_key"), DEFAULT_SECRET_KEY, None)
    assert not sr._is_configured(_definition("node_agent_api_key"), DEFAULT_NODE_AGENT_KEY, None)


def test_panel_port_default_matches_shared_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.panel_port_firewall import _panel_port

    monkeypatch.delenv("BACKEND_PORT", raising=False)
    assert _panel_port() == DEFAULT_BACKEND_PORT
