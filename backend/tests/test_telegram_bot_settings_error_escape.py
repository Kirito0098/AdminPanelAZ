"""Settings, unlock-code and config bot replies use parse_mode=HTML: error texts and names must be escaped."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.models import UserRole
from app.services.telegram_bot_handlers import (
    configs,
    settings,
    settings_admin_notify,
    settings_backups,
    settings_fsm,
    settings_monitor,
    settings_security,
    unlock_codes,
)

EVIL = '<b>x</b>&<a href="https://evil.example">y</a>'
SAFE = "&lt;b&gt;x&lt;/b&gt;&amp;&lt;a href=&quot;https://evil.example&quot;&gt;y&lt;/a&gt;"

_HANDLER_MODULES = (
    settings,
    settings_admin_notify,
    settings_backups,
    settings_monitor,
    settings_security,
    unlock_codes,
    configs,
)


def _ctx():
    return SimpleNamespace(
        db=None,
        bot_token="bot",
        chat_id=1,
        telegram_user_id="1",
        user=SimpleNamespace(id=1, username="admin", role=UserRole.admin),
        settings=None,
        mini_app_url="",
    )


def _boom(*_args, **_kwargs):
    raise ValueError(EVIL)


async def _allow(_ctx):
    return True


@pytest.fixture
def sent(monkeypatch):
    messages: list[str] = []

    async def fake_send_message(_token, _chat, text, **_kw):
        messages.append(text)

    async def fake_send_or_edit(_ctx, text, **_kw):
        messages.append(text)

    for module in _HANDLER_MODULES:
        monkeypatch.setattr(module, "send_message", fake_send_message)
        monkeypatch.setattr(module, "_require_admin_ctx", _allow, raising=False)
    monkeypatch.setattr(configs, "send_or_edit", fake_send_or_edit)
    monkeypatch.setattr(unlock_codes, "send_or_edit", fake_send_or_edit)
    monkeypatch.setattr(settings_fsm, "clear_pending", lambda _tg: None)
    return messages


def _pending(monkeypatch, field: str) -> None:
    monkeypatch.setattr(settings_fsm, "get_pending", lambda _tg: settings_fsm.PendingInput(field=field))


def _assert_escaped(messages: list[str]) -> None:
    assert len(messages) == 1
    assert SAFE in messages[0]
    assert "<a href" not in messages[0]


@pytest.mark.parametrize(
    ("module", "patch_name", "data"),
    [
        (settings, "_apply_telegram_patch", "st:tg:ne:1"),
        (settings_admin_notify, "_apply_admin_notify_patch", "st:an:all:1"),
        (settings_backups, "_apply_backup_settings_patch", "st:bk:auto:1"),
        (settings_security, "_apply_security_patch", "st:sec:ip:1"),
    ],
)
def test_settings_callback_value_error_is_escaped(sent, monkeypatch, module, patch_name, data):
    monkeypatch.setattr(module, patch_name, _boom)

    asyncio.run(settings.handle_settings_callback(_ctx(), data, message_id=None))

    _assert_escaped(sent)


@pytest.mark.parametrize(
    ("module", "patch_name", "field", "text"),
    [
        (settings, "_apply_telegram_patch", "user", "bot_name"),
        (settings_admin_notify, "_apply_admin_notify_patch", "an_tgid", "123"),
        (settings_monitor, "_apply_monitor_patch", "mon_cpu", "50"),
        (settings_backups, "_apply_backup_settings_patch", "bk_days", "3"),
    ],
)
def test_settings_text_value_error_is_escaped(sent, monkeypatch, module, patch_name, field, text):
    _pending(monkeypatch, field)
    monkeypatch.setattr(module, patch_name, _boom)

    asyncio.run(settings.handle_settings_text(_ctx(), text))

    _assert_escaped(sent)


def test_unlock_codes_callback_value_error_is_escaped(sent, monkeypatch):
    monkeypatch.setattr(
        unlock_codes,
        "get_pending",
        lambda _tg: SimpleNamespace(step="mode", grant_days=30, protocols=("openvpn",)),
    )
    monkeypatch.setattr(unlock_codes, "create_unlock_code", _boom)

    asyncio.run(unlock_codes.handle_unlock_codes_callback(_ctx(), "uc:mode:single", message_id=None))

    _assert_escaped(sent)


def test_unlock_codes_text_value_error_is_escaped(sent, monkeypatch):
    monkeypatch.setattr(unlock_codes, "get_pending", lambda _tg: SimpleNamespace(step="grant_days"))
    monkeypatch.setattr(unlock_codes, "_parse_grant_days", _boom)

    asyncio.run(unlock_codes.handle_unlock_codes_text(_ctx(), "5"))

    _assert_escaped(sent)


def _config(name: str = EVIL):
    return SimpleNamespace(id=7, client_name=name, vpn_type=SimpleNamespace(value="openvpn"))


def _group(key: str, files: int = 1):
    return SimpleNamespace(
        key=key,
        emoji="📄",
        title=key.upper(),
        files=[SimpleNamespace(index=i, file={"name": f"f{i}"}) for i in range(files)],
    )


def test_configs_list_preview_escapes_client_names():
    text = configs._configs_preview([_config()], 1, {}, filter_key="all")

    assert SAFE in text
    assert "<a href" not in text


def test_config_not_found_escapes_requested_name(sent, monkeypatch):
    monkeypatch.setattr(configs, "find_config_by_name", lambda _db, _user, _name: None)

    asyncio.run(configs.handle_config(_ctx(), EVIL))

    _assert_escaped(sent)


def test_config_protocol_picker_escapes_client_name(sent, monkeypatch):
    monkeypatch.setattr(configs, "_load_profile_groups", lambda _ctx, _cfg: [_group("ovpn"), _group("wg")])

    asyncio.run(configs._show_config_picker(_ctx(), _config()))

    _assert_escaped(sent)


def test_config_file_picker_escapes_client_name(sent, monkeypatch):
    monkeypatch.setattr(configs, "file_preview_line", lambda offset, _file: f"{offset}. file")
    monkeypatch.setattr(configs, "file_button_label", lambda _file, index: str(index))

    asyncio.run(configs._show_config_group_picker(_ctx(), _config(), _group("ovpn", files=2)))

    _assert_escaped(sent)


@pytest.mark.parametrize(("sent_count", "error"), [(1, None), (0, EVIL)])
def test_config_file_send_escapes_name_and_error(sent, monkeypatch, sent_count, error):
    async def _accessible(_ctx, _config_id):
        return _config()

    adapter = SimpleNamespace(get_profile_files=lambda _name, _type: [{"path": "/x"}])
    monkeypatch.setattr(configs, "_get_accessible_config", _accessible)
    monkeypatch.setattr(configs, "VpnType", lambda value: value)
    monkeypatch.setattr(configs, "get_active_adapter", lambda _db: adapter)
    monkeypatch.setattr(configs, "resolve_effective_visible_vpn_profiles", lambda _db, _user: None)
    monkeypatch.setattr(configs, "filter_profile_files", lambda files, _policy: files)
    monkeypatch.setattr(configs, "enrich_profile_files", lambda _name, files: files)
    monkeypatch.setattr(configs, "send_config_for_user", lambda *_a, **_k: (sent_count, error))

    asyncio.run(configs.handle_config_file_send(_ctx(), 7, 0))

    _assert_escaped(sent)
