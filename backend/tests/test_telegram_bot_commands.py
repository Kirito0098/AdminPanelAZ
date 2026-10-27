"""Per-role Telegram command lists: users get the base list, admins the full one."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserRole
from app.services import telegram_bot_commands as commands

ADMIN_ONLY = {"settings", "nodes", "cidr", "warper", "awg2", "unlock"}


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    session = make()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def calls(monkeypatch):
    recorded: list[tuple[str, list[str], dict | None]] = []

    def fake(token, command_list, *, scope=None):
        recorded.append((token, [item["command"] for item in command_list], scope))
        return True, ""

    monkeypatch.setattr(commands, "set_my_commands_sync", fake)
    monkeypatch.setattr(
        commands, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda _name: True)
    )
    return recorded


def test_default_scope_gets_the_user_list(db, calls):
    commands.sync_bot_commands(db, "token")

    token, names, scope = calls[0]
    assert token == "token"
    assert scope is None
    assert set(names) & ADMIN_ONLY == set()
    assert {"start", "myconfigs", "configs", "traffic", "status", "link", "help"} == set(names)


def test_linked_admin_gets_a_chat_scope_with_admin_commands(db, calls):
    db.add(User(username="boss", password_hash="x", role=UserRole.admin, telegram_id="777"))
    db.commit()

    commands.sync_bot_commands(db, "token")

    token, names, scope = calls[-1]
    assert scope == {"type": "chat", "chat_id": 777}
    assert ADMIN_ONLY <= set(names)


def test_admin_without_a_telegram_binding_is_skipped(db, calls):
    db.add(User(username="boss", password_hash="x", role=UserRole.admin, telegram_id=None))
    db.commit()

    commands.sync_bot_commands(db, "token")

    assert [call[2] for call in calls] == [None]


def test_disabled_features_drop_their_commands(db, calls, monkeypatch):
    monkeypatch.setattr(
        commands,
        "get_feature_service",
        lambda: SimpleNamespace(is_enabled=lambda name: name != "unlock_codes"),
    )
    db.add(User(username="boss", password_hash="x", role=UserRole.admin, telegram_id="777"))
    db.commit()

    commands.sync_bot_commands(db, "token")

    _, names, _ = calls[-1]
    assert "unlock" not in names
    assert "nodes" in names


def test_sync_admin_chat_commands_uses_the_admin_list(monkeypatch):
    recorded = []

    async def fake(token, command_list, *, scope=None):
        recorded.append((token, [item["command"] for item in command_list], scope))
        return True, ""

    monkeypatch.setattr(commands, "set_my_commands", fake)
    monkeypatch.setattr(
        commands, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda _name: True)
    )

    assert asyncio.run(commands.sync_admin_chat_commands("token", " 777 ")) is True
    token, names, scope = recorded[0]
    assert token == "token"
    assert scope == {"type": "chat", "chat_id": 777}
    assert ADMIN_ONLY <= set(names)


def test_set_my_commands_sync_sends_the_scope(monkeypatch):
    from app.services import telegram_api, telegram_transport

    captured: dict = {}

    def fake_post(_token, method, json=None, **_kwargs):
        captured.update(method=method, payload=json)
        return {"ok": True, "result": True}

    monkeypatch.setattr(telegram_transport, "bot_api_post_sync", fake_post)

    ok, error = telegram_api.set_my_commands_sync(
        "token", [{"command": "start", "description": "x"}], scope={"type": "chat", "chat_id": 1}
    )

    assert (ok, error) == (True, "")
    assert captured["method"] == "setMyCommands"
    assert captured["payload"] == {
        "commands": [{"command": "start", "description": "x"}],
        "scope": {"type": "chat", "chat_id": 1},
    }


def test_sync_admin_chat_commands_skips_non_numeric_chat(monkeypatch):
    async def fake(*_args, **_kwargs):  # pragma: no cover — не должен вызываться
        raise AssertionError("setMyCommands must not be called")

    monkeypatch.setattr(commands, "set_my_commands", fake)

    assert asyncio.run(commands.sync_admin_chat_commands("token", "not-a-chat")) is False
