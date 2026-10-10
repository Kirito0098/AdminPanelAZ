"""Bot replies use parse_mode=HTML: names, hosts and error texts must be escaped."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.models import Node, NodeStatus, UserRole
from app.services import telegram_api, telegram_bot_data
from app.services.telegram_bot_handlers import (
    awg2_status,
    cidr_status,
    nodes,
    start,
    status,
    traffic,
    warper_status,
)

EVIL = '<b>x</b>&<a href="https://evil.example">y</a>'
SAFE = "&lt;b&gt;x&lt;/b&gt;&amp;&lt;a href=&quot;https://evil.example&quot;&gt;y&lt;/a&gt;"


def _ctx(username: str = "admin"):
    return SimpleNamespace(
        db=None,
        bot_token="bot",
        chat_id=1,
        telegram_user_id="1",
        user=SimpleNamespace(id=1, username=username, role=UserRole.admin),
        settings=None,
        mini_app_url="",
    )


@pytest.fixture
def sent(monkeypatch):
    messages: list[str] = []

    async def fake_send_or_edit(_ctx, text, **_kw):
        messages.append(text)

    async def fake_send_message(_token, _chat, text, **_kw):
        messages.append(text)

    for module in (awg2_status, warper_status, cidr_status, traffic, status, start):
        monkeypatch.setattr(module, "send_or_edit", fake_send_or_edit, raising=False)
        monkeypatch.setattr(module, "send_message", fake_send_message, raising=False)
    monkeypatch.setattr(telegram_api, "send_message", fake_send_message)
    return messages


def _enabled():
    return SimpleNamespace(is_enabled=lambda _key: True)


def test_node_card_escapes_name_host_and_metadata():
    node = Node(
        id=5,
        name=EVIL,
        host=EVIL,
        port=9100,
        is_local=False,
        status=NodeStatus.online,
        node_metadata=json.dumps(
            {"server_ip": EVIL, "agent_version": EVIL, "antizapret_version": EVIL, "last_error": EVIL}
        ),
    )

    text = nodes._format_node_card(node, active_id=None)

    assert "<a href" not in text
    assert text.count(SAFE) == 6


def test_awg2_text_escapes_payload_strings():
    text = awg2_status._format_awg2_text(
        {
            "installed": False,
            "health_error": EVIL,
            "missing_components": [EVIL],
            "install_command": EVIL,
            "node_name": EVIL,
            "node_host": EVIL,
            "ifaces_summary": EVIL,
            "top_traffic": [{"name": EVIL, "rx": 1, "tx": 2}],
        }
    )

    assert "<a href" not in text
    assert text.count(SAFE) == 7


def test_traffic_top_lines_escape_client_names():
    text = traffic._format_top_lines([{"name": EVIL, "traffic_1d": 10, "is_active": True, "total_bytes": 10}])

    assert SAFE in text
    assert "<a href" not in text


def test_awg2_error_text_is_escaped(sent, monkeypatch):
    monkeypatch.setattr(awg2_status, "get_feature_service", _enabled)

    def boom(_db):
        raise RuntimeError(EVIL)

    monkeypatch.setattr(awg2_status, "build_awg2_status_payload", boom)

    asyncio.run(awg2_status.handle_awg2_status(_ctx()))

    assert SAFE in sent[0]


def test_warper_status_and_error_are_escaped(sent, monkeypatch):
    monkeypatch.setattr(warper_status, "get_feature_service", _enabled)
    monkeypatch.setattr(
        warper_status,
        "build_warper_status_payload",
        lambda _db: {"node_name": EVIL, "node_host": EVIL, "status": EVIL},
    )
    asyncio.run(warper_status.handle_warper_status(_ctx()))

    def boom(_db):
        raise RuntimeError(EVIL)

    monkeypatch.setattr(warper_status, "build_warper_status_payload", boom)
    asyncio.run(warper_status.handle_warper_status(_ctx()))

    assert sent[0].count(SAFE) == 3
    assert SAFE in sent[1]
    assert all("<a href" not in text for text in sent)


def test_cidr_error_is_escaped(sent, monkeypatch):
    def boom(_db):
        raise RuntimeError(EVIL)

    monkeypatch.setattr(cidr_status, "_format_cidr_status", boom)

    asyncio.run(cidr_status.handle_cidr_status(_ctx()))

    assert SAFE in sent[0]


def test_status_escapes_node_name_and_ip(sent, monkeypatch):
    monkeypatch.setattr(
        status,
        "build_dashboard_summary",
        lambda _db, _user: {
            "node_name": EVIL,
            "server_ip": EVIL,
            "total_configs": 0,
            "connected_openvpn": 0,
            "connected_wireguard": 0,
            "timestamp": "2026-10-10T10:00:00",
        },
    )
    monkeypatch.setattr(status, "build_server_status_block", lambda _db: None)

    asyncio.run(status.handle_status(_ctx()))

    assert sent[0].count(SAFE) == 2
    assert "<a href" not in sent[0]


def test_start_escapes_username(sent, monkeypatch):
    monkeypatch.setattr(start.settings_fsm, "clear_pending", lambda _tg: None)
    monkeypatch.setattr(start, "build_reply_keyboard", lambda _ctx: None)

    asyncio.run(start.handle_start(_ctx(username=EVIL)))

    assert SAFE in sent[0]
    assert "<a href" not in sent[0]


def test_server_status_unavailable_escapes_node_name(monkeypatch):
    class Broken:
        def get_server_metrics(self, **_kw):
            raise RuntimeError("down")

    monkeypatch.setattr(telegram_bot_data, "get_feature_service", _enabled)
    monkeypatch.setattr(telegram_bot_data, "get_active_adapter", lambda _db: Broken())
    monkeypatch.setattr(telegram_bot_data, "get_active_node", lambda _db: SimpleNamespace(name=EVIL))

    text = telegram_bot_data.build_server_status_block(None)

    assert SAFE in text
    assert "<a href" not in text
