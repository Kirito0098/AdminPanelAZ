"""Бот: конфиги абонента со всех его узлов, а не только с активного.

Жалоба: «пользователь не может переключиться между узлами» — в боте список
`/configs` фильтровался по активному узлу панели, поэтому конфиги на остальных
узлах были невидимы, а переход по ним отвечал «конфиг не найден».
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.services import telegram_bot_data
from app.services.node_manager import set_active_node_id
from app.services.profile_files import profile_files_batch_key
from app.services.telegram_bot_handlers import configs as handler
from app.services.telegram_bot_handlers.base import BotContext, load_telegram_bot_settings_snapshot


class FakeAdapter:
    """Узел-заглушка: один профиль на клиента, путь содержит имя узла."""

    def __init__(self, node_name: str) -> None:
        self.node_name = node_name
        self.calls: list[tuple[str, VpnType]] = []

    def _files(self, client_name: str) -> list[dict[str, str]]:
        return [
            {
                "path": f"/profiles/{self.node_name}/{client_name}.ovpn",
                "protocol": "openvpn",
                "variant": "antizapret-udp",
            }
        ]

    def get_profile_files(self, client_name: str, vpn_type: VpnType) -> list[dict[str, str]]:
        self.calls.append((client_name, vpn_type))
        return self._files(client_name)

    def get_profile_files_batch(self, clients):
        return {profile_files_batch_key(name, vpn_type): self._files(name) for name, vpn_type in clients}


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def nodes(db):
    germany = Node(
        name="Germany", host="127.0.0.1", port=9100, api_key_hash="h", api_key_encrypted="e",
        status=NodeStatus.online, is_local=True, node_kind="vpn", node_metadata="{}",
    )
    usa = Node(
        name="USA", host="127.0.0.2", port=9100, api_key_hash="h", api_key_encrypted="e",
        status=NodeStatus.online, is_local=False, node_kind="vpn", node_metadata="{}",
    )
    db.add_all([germany, usa])
    db.commit()
    db.refresh(germany)
    db.refresh(usa)
    set_active_node_id(db, germany.id)
    return germany, usa


@pytest.fixture()
def user(db):
    row = User(username="ivan", password_hash="x", role=UserRole.user, telegram_id="111", is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def configs(db, nodes, user):
    germany, usa = nodes
    local = VpnConfig(node_id=germany.id, client_name="ivan", vpn_type=VpnType.openvpn, owner_id=user.id)
    remote = VpnConfig(node_id=usa.id, client_name="ivan-usa", vpn_type=VpnType.openvpn, owner_id=user.id)
    db.add_all([local, remote])
    db.commit()
    db.refresh(local)
    db.refresh(remote)
    shadow = VpnConfig(
        node_id=usa.id,
        client_name="ivan-shadow",
        vpn_type=VpnType.openvpn,
        owner_id=user.id,
        ha_primary_config_id=local.id,
    )
    db.add(shadow)
    db.commit()
    return local, remote


@pytest.fixture()
def ctx(db, user):
    return BotContext(
        db=db,
        bot_token="bot",
        chat_id=1,
        telegram_user_id="111",
        user=user,
        settings=load_telegram_bot_settings_snapshot(db),
    )


def test_list_user_configs_spans_all_nodes(db, nodes, user, configs):
    germany, usa = nodes

    rows = [(config.client_name, config.node_id) for config in telegram_bot_data.list_user_configs(db, user)]

    assert rows == [("ivan", germany.id), ("ivan-usa", usa.id)]


def test_accessible_config_is_found_on_a_non_active_node(ctx, nodes, configs):
    _local, remote = configs

    found = asyncio.run(handler._get_accessible_config(ctx, remote.id))

    assert found is not None and found.id == remote.id


def test_profile_groups_are_read_from_the_config_node(ctx, nodes, configs, monkeypatch):
    _local, remote = configs
    germany, usa = nodes
    adapters = {germany.id: FakeAdapter("Germany"), usa.id: FakeAdapter("USA")}
    monkeypatch.setattr(handler, "get_adapter_for_node", lambda node: adapters[node.id])

    groups = handler._load_profile_groups(ctx, remote)

    assert adapters[usa.id].calls == [("ivan-usa", VpnType.openvpn)]
    assert adapters[germany.id].calls == []
    assert [group.key for group in groups] == ["ovpn"]


def test_profile_groups_are_empty_when_the_node_is_gone(ctx, nodes, configs, monkeypatch):
    _local, remote = configs
    remote.node_id = 999
    monkeypatch.setattr(handler, "get_adapter_for_node", lambda _node: pytest.fail("узла нет"))

    assert handler._load_profile_groups(ctx, remote) == []


def test_config_file_is_sent_from_the_config_node(ctx, nodes, configs, monkeypatch):
    _local, remote = configs
    germany, usa = nodes
    adapters = {germany.id: FakeAdapter("Germany"), usa.id: FakeAdapter("USA")}
    monkeypatch.setattr(handler, "get_adapter_for_node", lambda node: adapters[node.id])
    sent: list[str | None] = []

    def fake_send(_db, _config, _user, *, bot_token, path, chat_id_override, run_async):
        sent.append(path)
        return 1, None

    async def fake_edit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(handler, "send_config_for_user", fake_send)
    monkeypatch.setattr(handler, "send_or_edit", fake_edit)

    asyncio.run(handler.handle_config_file_send(ctx, remote.id, 0))

    assert sent == ["/profiles/USA/ivan-usa.ovpn"]
    assert adapters[germany.id].calls == []


def test_empty_profile_file_is_not_sent_to_telegram(db, nodes, configs, monkeypatch):
    from app.models import User, UserRole
    from app.services import telegram_config_send as sender

    _germany, usa = nodes
    _local, remote = configs
    user = db.query(User).filter(User.username == "ivan").first()
    assert user.role == UserRole.user

    adapter = FakeAdapter("USA")
    adapter._files = lambda client_name: [  # type: ignore[method-assign]
        {"path": f"/profiles/USA/{client_name}.ovpn", "protocol": "openvpn", "variant": "antizapret-udp"}
    ]
    monkeypatch.setattr(sender, "get_adapter_for_node", lambda _node: adapter)
    monkeypatch.setattr(sender, "read_profile_file_for_delivery", lambda *_a, **_k: "")
    monkeypatch.setattr(sender, "send_tg_document_result", lambda *_a, **_k: pytest.fail("пустой файл не отправляем"))

    sent, error = sender.send_config_for_user(
        db,
        remote,
        user,
        bot_token="bot",
        chat_id_override=user.telegram_id,
        run_async=False,
    )

    assert sent == 0
    assert error == sender.EMPTY_PROFILE_FILE_ERROR
    assert usa.id == remote.node_id


def test_group_keyboard_hides_the_protocol_button_for_a_single_protocol():
    from app.services.telegram_profile_ui import ProfileFileEntry, ProfileFileGroup

    group = ProfileFileGroup(
        key="ovpn",
        emoji="🔐",
        title="OpenVPN",
        files=[
            ProfileFileEntry(index=0, file={"path": "/a.ovpn", "protocol": "openvpn"}),
            ProfileFileEntry(index=1, file={"path": "/b.ovpn", "protocol": "openvpn"}),
        ],
    )

    single = handler._config_group_keyboard(1, group, show_protocols=False)
    texts = [button["text"] for row in single["inline_keyboard"] for button in row]
    assert handler.i18n.BTN_CONFIG_BACK not in texts
    assert handler.i18n.BTN_ALL_CONFIGS in texts

    multi = handler._config_group_keyboard(1, group, show_protocols=True)
    texts = [button["text"] for row in multi["inline_keyboard"] for button in row]
    assert handler.i18n.BTN_CONFIG_BACK in texts


def test_parse_configs_callback_reads_the_node(nodes):
    _germany, usa = nodes

    assert handler.parse_configs_callback(f"configs:1:wg:{usa.id}") == (1, "wg", usa.id)
    assert handler.parse_configs_callback("configs:0:all") == (0, "all", 0)


def test_node_without_profile_files_is_marked_in_the_switcher(nodes, configs):
    germany, usa = nodes
    local, remote = configs

    markup = handler._configs_keyboard(
        [local],
        page=0,
        filter_key="all",
        protocol_map={local.id: frozenset({"ovpn"})},
        node_labels={germany.id: "Germany", usa.id: "USA"},
        all_configs=[local, remote],
    )

    labels = [button["text"] for row in markup["inline_keyboard"] for button in row if "callback_data" in button]
    assert any(text.startswith("⚠️ USA (1)") for text in labels)
    assert any(text.endswith("Germany (1)") and not text.startswith("⚠️") for text in labels)


def test_selecting_a_node_without_files_explains_why(ctx, nodes, configs, monkeypatch):
    _germany, usa = nodes
    sent: list[str] = []

    async def fake_send(_token, _chat, text, **_kwargs):
        sent.append(text)

    monkeypatch.setattr(handler, "send_message", fake_send)
    monkeypatch.setattr(handler, "_load_config_protocol_map", lambda _ctx, items: {
        item.id: frozenset({"ovpn"}) if item.node_id != usa.id else frozenset() for item in items
    })

    asyncio.run(handler.handle_configs(ctx, node_id=usa.id))

    assert sent and "нет файлов профилей" in sent[0]
    assert "USA" in sent[0]


def test_configs_preview_numbers_rows_from_one(nodes, configs):
    germany, _usa = nodes
    local, _remote = configs

    text = handler._configs_preview(
        [local],
        0,
        {local.id: frozenset({"ovpn"})},
        labels={germany.id: "Germany"},
    )

    assert text.startswith("1. ")
    assert "· Germany" not in text


def test_configs_keyboard_offers_a_node_filter(nodes, configs):
    germany, usa = nodes
    local, remote = configs

    markup = handler._configs_keyboard(
        [local, remote],
        page=0,
        filter_key="all",
        protocol_map={local.id: frozenset({"ovpn"}), remote.id: frozenset({"ovpn"})},
        node_labels={germany.id: "Germany", usa.id: "USA"},
        node_id=0,
    )

    callbacks = [
        button.get("callback_data")
        for row in markup["inline_keyboard"]
        for button in row
        if button.get("callback_data")
    ]
    assert "configs:0:all:0" in callbacks
    assert f"configs:0:all:{germany.id}" in callbacks
    assert f"configs:0:all:{usa.id}" in callbacks


def test_handle_configs_filters_by_the_selected_node(ctx, nodes, configs, monkeypatch):
    _germany, usa = nodes
    captured: dict[str, str] = {}

    async def fake_edit(_ctx, text, *, markup=None, message_id=None):
        captured["text"] = text

    monkeypatch.setattr(handler, "send_or_edit", fake_edit)
    monkeypatch.setattr(
        handler,
        "_load_config_protocol_map",
        lambda _ctx, items: {item.id: frozenset({"ovpn"}) for item in items},
    )

    asyncio.run(handler.handle_configs(ctx, node_id=usa.id))

    assert "ivan-usa" in captured["text"]
    assert "<code>ivan</code>" not in captured["text"]
