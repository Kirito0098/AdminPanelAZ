"""Role matrix: a regular user must never reach admin bot actions or admin mini endpoints."""

from __future__ import annotations

import ast
import asyncio
import pathlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth as auth_module
from app.database import Base
from app.models import User, UserRole
from app.services import telegram_api as telegram_api_module
from app.services import telegram_bot as bot_module
from app.services import telegram_bot_i18n as i18n
from app.services.telegram_bot_handlers import (
    access_requests,
    awg2_status,
    cidr_status,
    menu,
    nodes,
    settings,
    ui as ui_module,
    unlock_codes,
    warper_status,
)
from app.services.telegram_bot_handlers.base import BotContext, TelegramBotSettingsSnapshot

ADMIN_COMMANDS = ["/settings", "/unlock", "/nodes", "/cidr", "/warper", "/awg2"]
ADMIN_CALLBACKS = ["st:root", "uc:cancel", "nodes:0", "nav:settings"]


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
def sent(monkeypatch):
    calls: list[str] = []

    async def fake_send(_token, _chat_id, text, **_kwargs):
        calls.append(text)

    async def fake_edit(_token, _chat_id, _message_id, text, **_kwargs):
        calls.append(text)

    async def fake_answer(*_args, **_kwargs):
        return None

    modules = (
        bot_module,
        telegram_api_module,
        settings,
        unlock_codes,
        nodes,
        menu,
        cidr_status,
        warper_status,
        awg2_status,
        access_requests,
        ui_module,
    )
    for module in modules:
        if hasattr(module, "send_message"):
            monkeypatch.setattr(module, "send_message", fake_send)
        if hasattr(module, "edit_message_text"):
            monkeypatch.setattr(module, "edit_message_text", fake_edit)
        if hasattr(module, "answer_callback_query"):
            monkeypatch.setattr(module, "answer_callback_query", fake_answer)
    monkeypatch.setattr(
        bot_module.telegram_bot_command_rate_limit_service, "consume", lambda *_a, **_k: None
    )
    return calls


def _context(db, role: UserRole) -> BotContext:
    user = User(
        username=f"role_{role.value}",
        password_hash="x",
        role=role,
        is_active=True,
        telegram_id=f"100{role.value}",
    )
    db.add(user)
    db.commit()
    return BotContext(
        db=db,
        bot_token="token",
        chat_id=1,
        telegram_user_id=user.telegram_id,
        user=user,
        settings=TelegramBotSettingsSnapshot(
            bot_token="token",
            interactive_enabled=True,
            bot_username="bot",
            webhook_set_at="",
            webhook_secret_set=True,
            token_set=True,
        ),
        mini_app_url="",
    )


@pytest.mark.parametrize("command", ADMIN_COMMANDS)
def test_admin_command_is_refused_for_a_user(db, sent, command):
    ctx = _context(db, UserRole.user)

    asyncio.run(bot_module._dispatch_command(ctx, command, ""))

    assert sent and i18n.ADMIN_ONLY in sent[0]


@pytest.mark.parametrize("data", ADMIN_CALLBACKS)
def test_admin_callback_is_refused_for_a_user(db, sent, data):
    ctx = _context(db, UserRole.user)

    asyncio.run(bot_module._dispatch_callback(ctx, data, message_id=None))

    assert i18n.ADMIN_ONLY in "".join(sent)


def test_admin_reaches_the_settings_menu(db, sent):
    ctx = _context(db, UserRole.admin)

    asyncio.run(bot_module._dispatch_command(ctx, "/settings", ""))

    assert sent and i18n.ADMIN_ONLY not in sent[0]


def test_require_tg_mini_admin_rejects_a_regular_user():
    with pytest.raises(HTTPException) as excinfo:
        auth_module.require_tg_mini_admin(SimpleNamespace(role=UserRole.user, telegram_id="1"))

    assert excinfo.value.status_code == 403


def test_get_tg_mini_user_requires_a_telegram_binding():
    with pytest.raises(HTTPException) as excinfo:
        auth_module.get_tg_mini_user(SimpleNamespace(role=UserRole.admin, telegram_id=""))

    assert excinfo.value.status_code == 401


ADMIN_MINI_PREFIXES = (
    "/nodes",
    "/dashboard",
    "/warper/status",
    "/awg2/status",
    "/cidr/status",
    "/telegram-settings",
    "/self-service",
    "/check-bot-delivery",
)


def _dependency_names(node: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
    for default in defaults:
        if (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
            and isinstance(default.args[0], ast.Name)
        ):
            names.add(default.args[0].id)
    return names


def _mini_routes():
    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers" / "tg_mini"
    for file in sorted(root.glob("*.py")):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for deco in node.decorator_list:
                if (
                    isinstance(deco, ast.Call)
                    and isinstance(deco.func, ast.Attribute)
                    and deco.func.attr in {"get", "post", "put", "patch", "delete"}
                    and deco.args
                    and isinstance(deco.args[0], ast.Constant)
                ):
                    yield file.name, str(deco.args[0].value), node


def test_mini_admin_endpoints_require_the_admin_dependency():
    violations = [
        (file, path, node.name)
        for file, path, node in _mini_routes()
        if path.startswith(ADMIN_MINI_PREFIXES)
        and "require_tg_mini_admin" not in _dependency_names(node)
    ]

    assert violations == []


def test_mini_user_endpoints_require_a_telegram_binding():
    violations = [
        (file, path, node.name)
        for file, path, node in _mini_routes()
        if path.startswith(("/me/", "/configs", "/settings", "/visible-vpn-profiles"))
        and "get_tg_mini_user" not in _dependency_names(node)
    ]

    assert violations == []


@pytest.mark.parametrize("data", ["st:root", "uc:cancel", "nodes:0", "nd:7", "ndh:1", "nda:1", "ar:a:3"])
def test_dispatch_blocks_admin_callbacks_before_the_handler(db, sent, monkeypatch, data):
    """Fail-closed net: even a handler without its own gate must not run for a user."""
    called: list[str] = []

    async def recorder(*_args, **_kwargs):
        called.append(data)
        return True

    for module_name in ("settings", "unlock_codes", "nodes", "access_requests"):
        module = globals()[module_name]
        for attr in dir(module):
            if attr.startswith("handle_"):
                monkeypatch.setattr(module, attr, recorder, raising=False)

    ctx = _context(db, UserRole.user)
    asyncio.run(bot_module._dispatch_callback(ctx, data, message_id=None))

    assert called == []
    assert i18n.ADMIN_ONLY in "".join(sent)


def test_renew_request_callback_stays_available_to_users():
    assert bot_module._is_admin_callback("ar:ext") is False
    assert bot_module._is_admin_callback("ar:a:3") is True


def test_admin_reply_keyboard_has_no_user_only_actions(monkeypatch):
    monkeypatch.setattr(menu, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda _n: True))

    keyboard = menu.build_linked_reply_keyboard(is_admin=True)
    texts = [button["text"] for row in keyboard["keyboard"] for button in row]

    assert i18n.BTN_REQUEST_MORE_CONFIG not in texts
    assert i18n.BTN_REDEEM_UNLOCK not in texts
    assert i18n.BTN_MENU_CONFIGS in texts
    assert i18n.BTN_MENU_MORE in texts


def test_user_reply_keyboard_keeps_user_only_actions(monkeypatch):
    monkeypatch.setattr(menu, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda _n: True))

    keyboard = menu.build_linked_reply_keyboard(is_admin=False)
    texts = [button["text"] for row in keyboard["keyboard"] for button in row]

    assert i18n.BTN_REQUEST_MORE_CONFIG in texts
    assert i18n.BTN_REDEEM_UNLOCK in texts


def test_linked_keyboard_is_role_aware(db, monkeypatch):
    monkeypatch.setattr(menu, "get_feature_service", lambda: SimpleNamespace(is_enabled=lambda _n: True))

    admin_keyboard = menu.build_reply_keyboard(_context(db, UserRole.admin))
    texts = [button["text"] for row in admin_keyboard["keyboard"] for button in row]

    assert i18n.BTN_REQUEST_MORE_CONFIG not in texts


def test_mini_settings_hides_bot_state_from_a_regular_user(db, monkeypatch):
    from app.routers import tg_mini as mini_root
    from app.routers.tg_mini import settings as mini_settings_module

    user = User(username="plain", password_hash="x", role=UserRole.user, telegram_id="1")
    admin = User(username="boss", password_hash="x", role=UserRole.admin, telegram_id="2")
    db.add_all([user, admin])
    db.commit()
    monkeypatch.setattr(
        mini_settings_module,
        "get_active_adapter",
        lambda _db: SimpleNamespace(get_server_ip=lambda: "1.2.3.4"),
    )
    monkeypatch.setattr(mini_root, "_get_bot_token", lambda _db: "token")

    user_view = mini_settings_module.mini_settings(db=db, current_user=user)
    admin_view = mini_settings_module.mini_settings(db=db, current_user=admin)

    assert user_view["bot_configured"] is False
    assert admin_view["bot_configured"] is True
