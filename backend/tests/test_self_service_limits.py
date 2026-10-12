import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSetting
from app.services import self_service as ss
from app.services import telegram_bot_command_rate_limit as bot_rl


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'limits.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _put(db, key, value):
    db.add(AppSetting(key=key, value=value))
    db.commit()


def test_self_service_limits_defaults_when_unset(db):
    assert ss.get_self_service_limits(db) == {
        "quota_default": 5,
        "create_rate_max": 3,
        "create_rate_window_seconds": 3600,
    }


def test_self_service_limits_clamp_stored_values(db):
    _put(db, ss.SETTING_QUOTA_DEFAULT, "5000")
    _put(db, ss.SETTING_CREATE_RATE_MAX, "-7")
    _put(db, ss.SETTING_CREATE_RATE_WINDOW, "5")
    assert ss.get_self_service_limits(db) == {
        "quota_default": 1000,
        "create_rate_max": 0,
        "create_rate_window_seconds": 60,
    }


def test_self_service_limits_garbage_falls_back_to_default(db):
    _put(db, ss.SETTING_CREATE_RATE_WINDOW, "abc")
    assert ss.get_self_service_limits(db)["create_rate_window_seconds"] == 3600


def test_set_self_service_limits_partial_update_and_clamp(db):
    result = ss.set_self_service_limits(db, quota_default=12, create_rate_window_seconds=10**9)
    db.commit()
    assert result == {"quota_default": 12, "create_rate_max": 3, "create_rate_window_seconds": 86400}
    assert ss.get_self_service_limits(db) == result


def test_quota_payload_uses_clamped_window(db):
    _put(db, ss.SETTING_CREATE_RATE_WINDOW, "1")
    user = type("U", (), {"id": 1, "role": ss.UserRole.user, "config_quota": None, "can_create_configs": True})()
    payload = ss.build_quota_payload(db, user)
    assert payload["create_rate_window_seconds"] == 60
    assert payload["limit"] == 5


def test_create_rate_limit_returns_429_after_max(db):
    ss.set_self_service_limits(db, create_rate_max=2, create_rate_window_seconds=3600)
    db.commit()
    service = ss.UserConfigCreateRateLimitService()
    service.consume(db, 42)
    service.consume(db, 42)
    with pytest.raises(HTTPException) as exc:
        service.consume(db, 42)
    assert exc.value.status_code == 429


def test_create_rate_limit_zero_disables(db):
    ss.set_self_service_limits(db, create_rate_max=0)
    db.commit()
    service = ss.UserConfigCreateRateLimitService()
    for _ in range(10):
        service.consume(db, 42)


def test_bot_command_limits_defaults_and_clamp(db):
    assert bot_rl.get_bot_command_rate_limits(db) == {"max_requests": 30, "window_seconds": 60}
    result = bot_rl.set_bot_command_rate_limits(db, max_requests=5000, window_seconds=1)
    db.commit()
    assert result == {"max_requests": 1000, "window_seconds": 10}
    assert bot_rl.get_bot_command_rate_limits(db) == result


def test_bot_command_rate_limit_blocks_after_max(db, monkeypatch):
    monkeypatch.setattr(
        bot_rl, "get_settings", lambda: type("S", (), {"telegram_bot_command_rate_limit_enabled": True})()
    )
    bot_rl.set_bot_command_rate_limits(db, max_requests=2, window_seconds=60)
    db.commit()
    service = bot_rl.TelegramBotCommandRateLimitService()
    assert service.consume(db, "100") is None
    assert service.consume(db, "100") is None
    assert service.consume(db, "100") is not None
