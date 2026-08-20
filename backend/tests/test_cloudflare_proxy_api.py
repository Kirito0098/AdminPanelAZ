from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_admin
from app.config import get_settings
from app.database import Base, get_db
import app.models  # noqa: F401 — register ORM models on Base.metadata
from app.models import AppSetting, User
from app.routers import maintenance as maintenance_router
from app.services import cloudflare_proxy_settings as cps


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch):
    monkeypatch.setenv(cps.ENV_CLOUDFLARE_PROXY_ENABLED, "true")
    monkeypatch.setenv(cps.ENV_CLOUDFLARE_IPS_AUTO_UPDATE, "false")
    monkeypatch.setenv(cps.ENV_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS, "7")
    monkeypatch.setenv("DOMAIN", "panel.example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(maintenance_router.router, prefix="/api")
    app.dependency_overrides[require_admin] = lambda: MagicMock(spec=User, username="admin", id=1)

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c


def _setting_value(db, key: str) -> str | None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def test_get_cloudflare_proxy_settings_uses_persisted_state(client, db, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cps, "_ENV_FILE", tmp_path / ".env")
    db.add(AppSetting(key=cps.SETTING_CLOUDFLARE_PROXY_ENABLED, value="false"))
    db.add(AppSetting(key=cps.SETTING_CLOUDFLARE_IPS_AUTO_UPDATE, value="true"))
    db.add(AppSetting(key=cps.SETTING_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS, value="14"))
    db.add(AppSetting(key=cps.SETTING_LAST_SUCCESS_AT, value="2026-08-20T10:00:00+00:00"))
    db.add(AppSetting(key=cps.SETTING_LAST_HASH, value="hash-123"))
    db.add(AppSetting(key=cps.SETTING_LAST_ERROR, value=""))
    db.commit()

    resp = client.get("/api/settings/cloudflare-proxy")

    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["auto_update"] is True
    assert body["interval_days"] == 14
    assert body["last_success_at"] == "2026-08-20T10:00:00+00:00"
    assert body["last_hash"] == "hash-123"
    assert body["last_error"] is None


def test_patch_cloudflare_proxy_regenerates_nginx_on_enabled_toggle(client, db, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cps, "_ENV_FILE", tmp_path / ".env")

    with patch(
        "app.routers.maintenance.cloudflare_proxy_settings_service.regenerate_panel_nginx_for_cloudflare_proxy"
    ) as regen:
        resp = client.patch(
            "/api/settings/cloudflare-proxy",
            json={"enabled": False, "auto_update": True, "interval_days": 21},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["auto_update"] is True
    assert body["interval_days"] == 21
    regen.assert_called_once()
    assert _setting_value(db, cps.SETTING_CLOUDFLARE_PROXY_ENABLED) == "false"
    assert _setting_value(db, cps.SETTING_CLOUDFLARE_IPS_AUTO_UPDATE) == "true"
    assert _setting_value(db, cps.SETTING_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS) == "21"


def test_patch_cloudflare_proxy_skips_regeneration_when_enabled_unchanged(client):
    with patch(
        "app.routers.maintenance.cloudflare_proxy_settings_service.regenerate_panel_nginx_for_cloudflare_proxy"
    ) as regen:
        resp = client.patch("/api/settings/cloudflare-proxy", json={"auto_update": True})

    assert resp.status_code == 200
    regen.assert_not_called()


def test_patch_cloudflare_proxy_reverts_flags_when_regeneration_fails(client, db, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cps, "_ENV_FILE", tmp_path / ".env")

    with patch(
        "app.routers.maintenance.cloudflare_proxy_settings_service.regenerate_panel_nginx_for_cloudflare_proxy",
        side_effect=RuntimeError("nginx -t failed"),
    ) as regen:
        resp = client.patch(
            "/api/settings/cloudflare-proxy",
            json={"enabled": False},
        )

    assert resp.status_code == 500
    assert "Не удалось перегенерировать конфигурацию nginx" in resp.json()["detail"]
    assert "nginx -t failed" in resp.json()["detail"]
    regen.assert_called_once()
    assert _setting_value(db, cps.SETTING_CLOUDFLARE_PROXY_ENABLED) == "true"


def test_refresh_cloudflare_proxy_forwards_force_flag(client):
    result = {
        "success": True,
        "applied": True,
        "forced": True,
        "changed": True,
        "hash": "hash-xyz",
        "message": "refreshed",
        "state": {
            "enabled": True,
            "auto_update": False,
            "interval_days": 7,
            "last_success_at": "2026-08-20T10:01:00+00:00",
            "last_hash": "hash-xyz",
            "last_error": None,
        },
    }
    with patch(
        "app.routers.maintenance.cloudflare_proxy_settings_service.refresh_cloudflare_ips",
        return_value=result,
    ) as refresh:
        resp = client.post("/api/settings/cloudflare-proxy/refresh", json={"force": True})

    assert resp.status_code == 200
    assert resp.json()["forced"] is True
    refresh.assert_called_once()
    assert refresh.call_args.kwargs["force"] is True
