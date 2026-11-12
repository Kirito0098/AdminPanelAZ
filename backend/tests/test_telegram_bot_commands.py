"""Дефолтное меню команд Telegram видят и гости — в нём только публичные команды."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services import telegram_bot_commands as commands_module
from app.services import telegram_bot_i18n as i18n


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_public_command_list_is_start_link_help():
    assert [command for command, _ in i18n.BOT_COMMANDS_PUBLIC] == ["start", "link", "help"]


def test_default_scope_gets_only_public_commands(db, monkeypatch):
    recorded: list[tuple[object, list[dict[str, str]]]] = []

    def fake_set(_token, commands, scope=None):
        recorded.append((scope, commands))
        return True, None

    monkeypatch.setattr(commands_module, "set_my_commands_sync", fake_set)

    result = commands_module.sync_bot_commands(db, "token")

    assert result["default"] is True
    scope, commands = recorded[0]
    assert scope is None
    assert [item["command"] for item in commands] == ["start", "link", "help"]


def test_admin_list_still_contains_user_and_admin_commands():
    admin_commands = {command for command, _ in i18n.BOT_COMMANDS_ADMIN}
    assert {"myconfigs", "traffic", "admin", "status", "unlock"} <= admin_commands
