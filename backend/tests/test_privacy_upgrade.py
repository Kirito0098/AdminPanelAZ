"""Task 14: privacy upgrade steps 1–5 are idempotent."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AppSetting, User, UserConfigAccess, UserRole
from app.services import privacy_upgrade
from app.services.app_setting_store import _get_setting, _set_setting
from app.services.qr_download import is_stored_pin_hash, verify_pin


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _seed_pre_2266(db) -> User:
    """DB state mimicking an install before privacy upgrade."""
    user = User(username="grantee", password_hash="x", role=UserRole.user)
    db.add(user)
    db.flush()
    db.add(UserConfigAccess(user_id=user.id, config_group="ivan"))
    db.add(UserConfigAccess(user_id=user.id, config_group="fam*"))
    _set_setting(db, "qr_download_pin", "654321")  # plain text
    _set_setting(db, "telegram_chat_id", "101,-100999")
    _set_setting(db, "telegram_bot_token", "123:ABC")
    _set_setting(db, "telegram_bot_interactive_enabled", "true")
    _set_setting(db, "telegram_webhook_set_at", "2026-01-01T00:00:00+00:00")
    _set_setting(db, "telegram_webhook_secret", "whsec")
    # secret_required unset — pre-2.26.6 webhook without header enforcement
    db.commit()
    return user


def _grant_groups(db, user_id: int) -> list[str]:
    return sorted(
        r.config_group
        for r in db.query(UserConfigAccess).filter_by(user_id=user_id).all()
    )


def _snapshot(db, user_id: int) -> dict:
    return {
        "grants": _grant_groups(db, user_id),
        "prefix_marker": _get_setting(db, "config_access_explicit_prefix", ""),
        "pin_is_hash": is_stored_pin_hash(_get_setting(db, "qr_download_pin", "")),
        "pin_verifies": verify_pin("654321", _get_setting(db, "qr_download_pin", "")),
        "webhook_secret_required": _get_setting(db, "telegram_webhook_secret_required", ""),
        "webhook_privacy_upgraded": _get_setting(db, privacy_upgrade.WEBHOOK_PRIVACY_UPGRADED, ""),
        "group_pause_warned": _get_setting(db, "backup_group_pause_warned", ""),
        "nginx_privacy_applied": _get_setting(db, privacy_upgrade.NGINX_PRIVACY_APPLIED, ""),
    }


def test_privacy_upgrade_twice_same_end_state(monkeypatch, db):
    user = _seed_pre_2266(db)
    webhook_calls: list[dict] = []
    nginx_calls: list[int] = []
    notices: list[dict] = []

    monkeypatch.setattr(
        privacy_upgrade,
        "get_webhook_info_sync",
        lambda _token: (True, {"url": "https://panel.example/api/telegram/webhook/oldsec"}),
    )
    monkeypatch.setattr(
        privacy_upgrade,
        "set_webhook_sync",
        lambda token, url, *, secret_token=None: webhook_calls.append(
            {"token": token, "url": url, "secret_token": secret_token}
        )
        or (True, ""),
    )
    monkeypatch.setattr(
        privacy_upgrade,
        "ensure_nginx_privacy_log",
        lambda: nginx_calls.append(1) or True,
    )
    monkeypatch.setattr(
        "app.services.admin_notify.admin_notify_service.send_settings_change",
        lambda _db, **kwargs: notices.append(kwargs),
    )

    first = privacy_upgrade.run_privacy_upgrade(db)
    snap1 = _snapshot(db, user.id)

    assert first["grants_changed"] == 1
    assert snap1["grants"] == ["fam*", "ivan*"]
    assert snap1["prefix_marker"] == "1"
    assert snap1["pin_is_hash"] is True
    assert snap1["pin_verifies"] is True
    assert snap1["webhook_secret_required"] in ("1", "true")
    assert snap1["webhook_privacy_upgraded"] == "1"
    assert snap1["group_pause_warned"] == "1"
    assert snap1["nginx_privacy_applied"] == "1"
    assert len(webhook_calls) == 1
    assert webhook_calls[0]["secret_token"] == "whsec"
    assert webhook_calls[0]["url"] == "https://panel.example/api/telegram/webhook/whsec"
    assert len(nginx_calls) == 1
    assert notices  # group-pause warning

    second = privacy_upgrade.run_privacy_upgrade(db)
    snap2 = _snapshot(db, user.id)

    assert snap2 == snap1
    assert second["grants_changed"] == 0
    assert second["pin_migrated"] is False
    assert len(webhook_calls) == 1  # no second setWebhook
    assert len(nginx_calls) == 1


def test_webhook_failure_does_not_require_secret_or_silence_bot(monkeypatch, db):
    _seed_pre_2266(db)
    monkeypatch.setattr(
        privacy_upgrade,
        "get_webhook_info_sync",
        lambda _token: (True, {"url": "https://panel.example/api/telegram/webhook/oldsec"}),
    )
    monkeypatch.setattr(
        privacy_upgrade,
        "set_webhook_sync",
        lambda *_a, **_k: (False, "network unreachable"),
    )
    monkeypatch.setattr(privacy_upgrade, "ensure_nginx_privacy_log", lambda: True)
    monkeypatch.setattr(
        "app.services.admin_notify.admin_notify_service.send_settings_change",
        lambda *_a, **_k: None,
    )

    privacy_upgrade.run_privacy_upgrade(db)

    assert _get_setting(db, "telegram_webhook_secret_required", "") != "true"
    assert _get_setting(db, "telegram_webhook_secret_required", "") != "1"
    assert _get_setting(db, privacy_upgrade.WEBHOOK_PRIVACY_UPGRADED, "") != "1"
    # Grants / PIN still applied
    assert _get_setting(db, "config_access_explicit_prefix", "") == "1"
    assert is_stored_pin_hash(_get_setting(db, "qr_download_pin", ""))


def test_webhook_skipped_when_not_registered(monkeypatch, db):
    _seed_pre_2266(db)
    _set_setting(db, "telegram_webhook_set_at", "")
    db.commit()
    calls: list = []
    monkeypatch.setattr(
        privacy_upgrade,
        "set_webhook_sync",
        lambda *_a, **_k: calls.append(1) or (True, ""),
    )
    monkeypatch.setattr(privacy_upgrade, "ensure_nginx_privacy_log", lambda: True)
    monkeypatch.setattr(
        "app.services.admin_notify.admin_notify_service.send_settings_change",
        lambda *_a, **_k: None,
    )

    privacy_upgrade.run_privacy_upgrade(db)
    assert calls == []
    assert _get_setting(db, privacy_upgrade.WEBHOOK_PRIVACY_UPGRADED, "") == "1"


def test_to_response_nulls_owner_id_for_grantee(monkeypatch):
    from datetime import datetime

    from app.models import VpnType
    from app.routers import configs as configs_router
    from app.schemas import VpnConfigResponse

    owner = SimpleNamespace(id=1, username="alice")
    viewer = SimpleNamespace(id=2, role=UserRole.user)
    config = SimpleNamespace(
        id=10,
        client_name="alice",
        vpn_type=VpnType.wireguard,
        owner_id=1,
        cert_expire_days=None,
        cert_expires_at=None,
        expires_at=None,
        description=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        sync_group_id=None,
    )

    class _UQ:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return owner

    db = SimpleNamespace(query=lambda *_a: _UQ())
    monkeypatch.setattr(configs_router, "_ha_info_for_config", lambda *_a: None)

    resp = configs_router._to_response(config, db, viewer=viewer)
    assert isinstance(resp, VpnConfigResponse)
    assert resp.owner_username is None
    assert resp.owner_id is None

    own = configs_router._to_response(config, db, viewer=SimpleNamespace(id=1, role=UserRole.user))
    assert own.owner_id == 1
    assert own.owner_username == "alice"
