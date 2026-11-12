"""Unlinked Telegram login alerts must stay damped across panel restarts."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services import admin_notify
from app.services.admin_notify import AdminNotifyService
from app.services.app_setting_store import _get_setting, _set_setting


@pytest.fixture
def session_factory(monkeypatch):
    """Same on-disk DB for every state session, like the real SessionLocal."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(admin_notify, "_open_notify_state_session", lambda: factory())
    return factory


@pytest.fixture
def sent(monkeypatch):
    service = AdminNotifyService()
    calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        service,
        "send",
        lambda db, event_type, **kwargs: calls.append((event_type, kwargs.get("target_name"))),
    )
    return service, calls


def _read_state(factory) -> dict:
    db = factory()
    try:
        raw = _get_setting(db, admin_notify._UNLINKED_STATE_KEY, "{}")
    finally:
        db.close()
    return json.loads(raw)


def _write_state(factory, state: dict) -> None:
    db = factory()
    try:
        _set_setting(db, admin_notify._UNLINKED_STATE_KEY, json.dumps(state), commit=True)
    finally:
        db.close()


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) - delta).isoformat()


def test_first_alert_is_sent_and_second_is_suppressed(session_factory, sent):
    service, calls = sent
    db = MagicMock()

    service.send_tg_login_unlinked(db, telegram_id="6028369631", mini=True)
    service.send_tg_login_unlinked(db, telegram_id="6028369631", mini=True)

    assert calls == [("tg_mini_login_unlinked", "6028369631")]
    assert "6028369631" in _read_state(session_factory)["cooldowns"]


def test_cooldown_survives_service_restart(session_factory, sent):
    service, calls = sent
    db = MagicMock()
    service.send_tg_login_unlinked(db, telegram_id="111", mini=True)

    restarted, restarted_calls = AdminNotifyService(), []
    restarted.send = lambda db, event_type, **kwargs: restarted_calls.append(kwargs.get("target_name"))
    restarted.send_tg_login_unlinked(db, telegram_id="111", mini=True)

    assert calls == [("tg_mini_login_unlinked", "111")]
    assert restarted_calls == []


def test_alert_resumes_after_persisted_cooldown_expires(session_factory, sent):
    service, calls = sent
    db = MagicMock()
    service.send_tg_login_unlinked(db, telegram_id="111", mini=True)

    _write_state(
        session_factory,
        {"cooldowns": {"111": _iso(timedelta(seconds=61))}, "mini": [_iso(timedelta(minutes=5))]},
    )
    restarted = AdminNotifyService()
    restarted.send = lambda *a, **k: calls.append(k.get("target_name"))
    restarted.send_tg_login_unlinked(db, telegram_id="111", mini=True)

    assert calls == [("tg_mini_login_unlinked", "111"), "111"]


def test_global_limit_caps_distinct_accounts(session_factory, sent):
    service, calls = sent
    db = MagicMock()

    for tg_id in ("1", "2", "3", "4", "5", "6", "7"):
        service.send_tg_login_unlinked(db, telegram_id=tg_id, mini=True)

    assert len(calls) == AdminNotifyService._UNLINKED_MINI_LIMIT
    state = _read_state(session_factory)
    assert len(state["mini"]) == AdminNotifyService._UNLINKED_MINI_LIMIT
    # Suppressed accounts do not get a cooldown entry: the alert is not "spent".
    assert "7" not in state["cooldowns"]


def test_global_limit_ignores_events_outside_window(session_factory, sent):
    service, calls = sent
    db = MagicMock()
    _write_state(
        session_factory,
        {"cooldowns": {}, "mini": [_iso(timedelta(minutes=11))] * 5},
    )

    service.send_tg_login_unlinked(db, telegram_id="777", mini=True)

    assert calls == [("tg_mini_login_unlinked", "777")]


def test_stale_cooldowns_are_pruned_and_key_is_bounded(session_factory, sent):
    service, calls = sent
    db = MagicMock()
    stale = {str(i): _iso(timedelta(days=2)) for i in range(300)}
    stale["fresh"] = _iso(timedelta(seconds=30))
    _write_state(session_factory, {"cooldowns": stale, "mini": [_iso(timedelta(minutes=30))]})

    service.send_tg_login_unlinked(db, telegram_id="999", mini=True)

    state = _read_state(session_factory)
    assert calls == [("tg_mini_login_unlinked", "999")]
    assert set(state["cooldowns"]) == {"fresh", "999"}
    assert len(state["mini"]) == 1
    assert len(state["cooldowns"]) <= AdminNotifyService._UNLINKED_COOLDOWN_MAX_IDS


def test_cooldown_key_keeps_only_newest_entries(session_factory, sent):
    service, _calls = sent
    db = MagicMock()
    overflow = {
        str(i): _iso(timedelta(minutes=i + 1))
        for i in range(AdminNotifyService._UNLINKED_COOLDOWN_MAX_IDS + 5)
    }
    _write_state(session_factory, {"cooldowns": overflow, "mini": []})

    service.send_tg_login_unlinked(db, telegram_id="new", mini=True)

    state = _read_state(session_factory)
    assert len(state["cooldowns"]) == AdminNotifyService._UNLINKED_COOLDOWN_MAX_IDS
    assert "new" in state["cooldowns"]


def test_non_mini_login_uses_same_persisted_cooldown(session_factory, sent):
    service, calls = sent
    db = MagicMock()

    service.send_tg_login_unlinked(db, telegram_id="555", mini=False)
    service.send_tg_login_unlinked(db, telegram_id="555", mini=True)

    assert calls == [("tg_login_unlinked", "555")]


def test_corrupted_state_does_not_block_alert(session_factory, sent):
    service, calls = sent
    db_state = session_factory()
    try:
        _set_setting(db_state, admin_notify._UNLINKED_STATE_KEY, "not json", commit=True)
    finally:
        db_state.close()

    service.send_tg_login_unlinked(MagicMock(), telegram_id="321", mini=True)

    assert calls == [("tg_mini_login_unlinked", "321")]


def test_blank_telegram_id_is_ignored(session_factory, sent):
    service, calls = sent

    service.send_tg_login_unlinked(MagicMock(), telegram_id="   ", mini=True)

    assert calls == []
    assert _read_state(session_factory) == {}
