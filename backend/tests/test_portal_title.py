"""Portal title: set in portal settings, neutral by default, no longer read from the legacy app_name key."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AppSetting
from app.routers.security import SecuritySettingsUpdate
from app.schemas import AppSettingsResponse
from app.services import client_portal as portal
from app.services import security as security_module
from app.services.security import SecurityService


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setattr(
        security_module,
        "cached_firewall_tools_status",
        lambda: SimpleNamespace(fully_ready=True, operational_detail=""),
    )
    monkeypatch.setattr(SecurityService, "is_whitelist_port_firewall_applicable", lambda self: False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_portal_title_defaults_to_a_neutral_word(db):
    assert portal._portal_brand_title(db) == "Подключение"


def test_legacy_app_name_key_is_ignored(db):
    db.add(AppSetting(key="app_name", value="My VPN"))
    db.commit()

    assert portal._portal_brand_title(db) == "Подключение"


def test_portal_title_comes_from_portal_settings(db):
    service = SecurityService()

    service.update_settings(db, {"portal_title": "  Семейный доступ  "})

    assert portal._portal_brand_title(db) == "Семейный доступ"
    assert service.get_settings(db)["portal_title"] == "Семейный доступ"


def test_cleared_portal_title_falls_back_to_the_neutral_word(db):
    service = SecurityService()
    service.update_settings(db, {"portal_title": "Дом"})

    service.update_settings(db, {"portal_title": ""})

    assert portal._portal_brand_title(db) == "Подключение"
    assert service.get_settings(db)["portal_title"] == ""


def test_portal_title_is_limited_to_64_characters():
    assert SecuritySettingsUpdate(portal_title="я" * 64).portal_title == "я" * 64
    with pytest.raises(ValidationError):
        SecuritySettingsUpdate(portal_title="я" * 65)


def test_app_settings_no_longer_expose_app_name():
    assert "app_name" not in AppSettingsResponse.model_fields
