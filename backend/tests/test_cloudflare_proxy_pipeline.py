from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import Base
from app.models import AppSetting
from app.services import cloudflare_proxy_settings as cps


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch):
    monkeypatch.setenv(cps.ENV_CLOUDFLARE_PROXY_ENABLED, "true")
    monkeypatch.setenv(cps.ENV_CLOUDFLARE_IPS_AUTO_UPDATE, "false")
    monkeypatch.setenv(cps.ENV_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS, "7")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _setting_value(db, key: str) -> str | None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def test_get_state_uses_env_defaults(db):
    state = cps.get_cloudflare_proxy_state(db)
    assert state["enabled"] is True
    assert state["auto_update"] is False
    assert state["interval_days"] == 7
    assert state["last_success_at"] is None
    assert state["last_hash"] is None
    assert state["last_error"] is None


def test_set_flags_persists_db_and_env(tmp_path: Path, db, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(cps, "_ENV_FILE", env_file)

    state = cps.set_cloudflare_proxy_flags(
        db,
        enabled=False,
        auto_update=True,
        interval_days=14,
    )

    assert state["enabled"] is False
    assert state["auto_update"] is True
    assert state["interval_days"] == 14
    assert _setting_value(db, cps.SETTING_CLOUDFLARE_PROXY_ENABLED) == "false"
    assert _setting_value(db, cps.SETTING_CLOUDFLARE_IPS_AUTO_UPDATE) == "true"
    assert _setting_value(db, cps.SETTING_CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS) == "14"

    env_text = env_file.read_text(encoding="utf-8")
    assert "CLOUDFLARE_PROXY_ENABLED=false" in env_text
    assert "CLOUDFLARE_IPS_AUTO_UPDATE=true" in env_text
    assert "CLOUDFLARE_IPS_UPDATE_INTERVAL_DAYS=14" in env_text


def test_refresh_noop_when_hash_matches(db):
    body = "set_real_ip_from 173.245.48.0/20;\n"
    with patch(
        "app.services.cloudflare_proxy_settings.fetch_cloudflare_realip_conf",
        return_value=(body, "hash-123"),
    ), patch("app.services.cloudflare_proxy_settings.subprocess.run") as run_mock:
        db.add(AppSetting(key=cps.SETTING_LAST_HASH, value="hash-123"))
        db.add(AppSetting(key=cps.SETTING_LAST_ERROR, value="stale"))
        db.commit()

        result = cps.refresh_cloudflare_ips(db)

    assert result["success"] is True
    assert result["applied"] is False
    assert result["changed"] is False
    assert result["message"] == "Списки IP Cloudflare не изменились; применение пропущено."
    assert run_mock.call_count == 0
    state = cps.get_cloudflare_proxy_state(db)
    assert state["last_hash"] == "hash-123"
    assert state["last_error"] is None
    assert state["last_success_at"] is not None
    datetime.fromisoformat(state["last_success_at"])


def test_refresh_updates_status_on_apply_failure(db):
    body = "set_real_ip_from 173.245.48.0/20;\n"
    run_result = MagicMock(returncode=1, stdout="", stderr="nginx -t failed")
    with patch(
        "app.services.cloudflare_proxy_settings.fetch_cloudflare_realip_conf",
        return_value=(body, "hash-456"),
    ), patch("app.services.cloudflare_proxy_settings.subprocess.run", return_value=run_result) as run_mock:
        result = cps.refresh_cloudflare_ips(db)

    assert result["success"] is False
    assert "Не удалось применить списки IP Cloudflare" in result["error"]
    assert "nginx -t failed" in result["error"]
    run_mock.assert_called_once()
    state = cps.get_cloudflare_proxy_state(db)
    assert state["last_hash"] is None
    assert "nginx -t failed" in (state["last_error"] or "")
    assert state["last_success_at"] is None


def test_refresh_applies_changed_hash_and_updates_status(db):
    body = "set_real_ip_from 173.245.48.0/20;\n"
    run_result = MagicMock(returncode=0, stdout="reload ok", stderr="")
    with patch(
        "app.services.cloudflare_proxy_settings.fetch_cloudflare_realip_conf",
        return_value=(body, "hash-789"),
    ), patch("app.services.cloudflare_proxy_settings.subprocess.run", return_value=run_result) as run_mock:
        result = cps.refresh_cloudflare_ips(db)

    assert result["success"] is True
    assert result["applied"] is True
    assert result["changed"] is True
    assert result["message"].startswith("Списки IP Cloudflare успешно обновлены.")
    run_mock.assert_called_once()
    args = run_mock.call_args.args[0]
    assert args[:3] == ["sudo", "-n", "bash"]
    assert args[3].endswith("nginx-cloudflare-realip-apply.sh")
    state = cps.get_cloudflare_proxy_state(db)
    assert state["last_hash"] == "hash-789"
    assert state["last_error"] is None
    assert state["last_success_at"] is not None
