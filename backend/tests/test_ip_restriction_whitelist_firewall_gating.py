"""Whitelist port firewall gating by publish mode."""

import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSetting
from app.services.env_file import EnvFileService
from app.services.panel_port_firewall import PanelPortFirewall
from app.services.security import SecurityService


@pytest.fixture()
def security_env(tmp_path, monkeypatch):
    db_path = tmp_path / "whitelist_fw.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "BACKEND_HOST=0.0.0.0",
                "BACKEND_PORT=8000",
                "BEHIND_NGINX=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        SecurityService,
        "_env_file",
        lambda self: EnvFileService(env_file),
    )

    session.add(AppSetting(key="security_ip_restriction", value="true"))
    session.add(AppSetting(key="security_allowed_ips", value="10.0.0.1"))
    session.add(AppSetting(key="security_whitelist_firewall", value="true"))
    session.commit()
    yield session, env_file
    session.close()


@patch.dict(os.environ, {"BACKEND_HOST": "127.0.0.1", "BEHIND_NGINX": "false"}, clear=False)
def test_sync_disables_when_local_http(security_env):
    session, env_file = security_env
    env_file.write_text("BACKEND_HOST=127.0.0.1\nBEHIND_NGINX=false\nBACKEND_PORT=8000\n", encoding="utf-8")
    service = SecurityService()

    with patch.object(PanelPortFirewall, "disable") as disable_mock, patch.object(
        PanelPortFirewall, "sync"
    ) as sync_mock:
        result = service.sync_whitelist_port_firewall(session)

    assert result is False
    disable_mock.assert_called_once()
    sync_mock.assert_not_called()
    settings = service.get_settings(session)
    assert settings["whitelist_firewall"] is False


@patch.dict(os.environ, {"BACKEND_HOST": "0.0.0.0", "BEHIND_NGINX": "false"}, clear=False)
def test_sync_applies_when_direct_http(security_env):
    session, _env_file = security_env
    service = SecurityService()

    with patch.object(PanelPortFirewall, "disable") as disable_mock, patch.object(
        PanelPortFirewall, "sync", return_value=True
    ) as sync_mock:
        result = service.sync_whitelist_port_firewall(session)

    assert result is True
    sync_mock.assert_called_once()
    assert "10.0.0.1" in sync_mock.call_args.args[0]
    disable_mock.assert_not_called()


@patch.dict(os.environ, {"BACKEND_HOST": "127.0.0.1", "BEHIND_NGINX": "true"}, clear=False)
def test_sync_disables_when_behind_nginx(security_env):
    session, env_file = security_env
    env_file.write_text("BACKEND_HOST=127.0.0.1\nBEHIND_NGINX=true\nBACKEND_PORT=8000\n", encoding="utf-8")
    service = SecurityService()

    with patch.object(PanelPortFirewall, "disable") as disable_mock, patch.object(
        PanelPortFirewall, "sync"
    ) as sync_mock:
        result = service.sync_whitelist_port_firewall(session)

    assert result is False
    disable_mock.assert_called_once()
    sync_mock.assert_not_called()


@patch.dict(os.environ, {"BACKEND_HOST": "0.0.0.0", "BEHIND_NGINX": "false"}, clear=False)
def test_is_whitelist_port_firewall_active(security_env):
    session, _env_file = security_env
    service = SecurityService()
    assert service.is_whitelist_port_firewall_active(session)

    row = session.query(AppSetting).filter(AppSetting.key == "security_whitelist_firewall").first()
    row.value = "false"
    session.commit()
    assert not service.is_whitelist_port_firewall_active(session)
