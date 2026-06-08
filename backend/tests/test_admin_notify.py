"""AdminNotify text building and delivery tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSetting, DEFAULT_TG_NOTIFY_EVENTS, User, UserRole
from app.services.admin_notify import AdminNotifyService


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def notify_service():
    return AdminNotifyService(logger_instance=MagicMock())


class AdminNotifyTextTests:
    def _build(self, service, event_type, **kwargs):
        return service._build_text(
            event_type,
            kwargs.get("actor_username"),
            kwargs.get("target_name"),
            kwargs.get("target_type"),
            kwargs.get("remote_addr"),
            kwargs.get("details"),
            kwargs.get("subject_name"),
            client_timezone=kwargs.get("client_timezone"),
        )

    def _lines(self, text):
        return (text or "").split("\n")


class TestAdminNotifyText(AdminNotifyTextTests):
    def setup_method(self):
        self.service = AdminNotifyService(logger_instance=MagicMock())

    def test_config_delete_four_line_layout(self):
        text = self._build(
            self.service,
            "config_delete",
            actor_username="Claymore",
            target_name="Test",
            target_type="openvpn",
        )
        assert text is not None
        lines = self._lines(text)
        assert len(lines) == 4
        assert "🗑️" in lines[0]
        assert "Удаление конфига" in lines[0]
        assert "👨‍💼" in lines[1]
        assert "<code>Claymore</code>" in lines[1]
        assert lines[2].startswith("Удалил")
        assert "🔐" in lines[2]
        assert "OpenVPN" in lines[2]
        assert "<code>Test</code>" in lines[2]

    def test_settings_change_uses_client_timezone(self):
        text = self._build(
            self.service,
            "settings_change",
            actor_username="admin1",
            target_name="settings_backup_create",
            subject_name="backup.tar.gz",
            client_timezone="Europe/Moscow",
        )
        lines = self._lines(text)
        assert len(lines) == 4
        assert lines[3].startswith("🕐 ")
        assert not lines[3].endswith(" UTC")

    def test_config_create_openvpn_narrative(self):
        text = self._build(
            self.service,
            "config_create",
            actor_username="admin1",
            target_name="client-a",
            target_type="openvpn",
        )
        assert text is not None
        lines = self._lines(text)
        assert len(lines) == 4
        assert "✨" in lines[0]
        assert lines[2].startswith("Создал")
        assert "🔐" in lines[2]
        assert "<code>client-a</code>" in lines[2]

    def test_login_success_four_line_layout(self):
        text = self._build(
            self.service,
            "login_success",
            actor_username="viewer1",
            remote_addr="203.0.113.10",
        )
        assert text is not None
        lines = self._lines(text)
        assert len(lines) == 4
        assert "👤" in lines[1]
        assert "Вошёл" in lines[2]
        assert "🌐" in lines[2]
        assert "<code>203.0.113.10</code>" in lines[2]

    def test_client_ban_temp_permanent_and_unblock(self):
        temp = self._build(
            self.service,
            "client_ban",
            actor_username="Claymore",
            target_name="Test",
            target_type="wireguard",
            details="action=temp_block days=7 block_until=2026-05-30 09:13:00",
        )
        permanent = self._build(
            self.service,
            "client_ban",
            actor_username="Claymore",
            target_name="Test",
            target_type="wireguard",
            details="action=permanent_block",
        )
        unblocked = self._build(
            self.service,
            "client_ban",
            actor_username="Claymore",
            target_name="Test",
            target_type="wireguard",
            details="action=unblock",
        )
        for text in (temp, permanent, unblocked):
            assert len(self._lines(text)) == 4

        assert "⏱️" in temp
        assert self._lines(temp)[2].startswith("Временно")
        assert "на 7 дн." in temp
        assert "2026-05-30" in temp
        assert "🛡️" in temp
        assert "WireGuard" in temp

        assert "Постоянная блокировка" in permanent
        assert "бессрочно" in self._lines(permanent)[2]

        assert "🟢" in unblocked
        assert self._lines(unblocked)[2].startswith("Разблокировал")

    def test_client_ban_legacy_blocked_flags(self):
        blocked = self._build(
            self.service,
            "client_ban",
            actor_username="admin",
            target_name="vpn-user",
            details="blocked=1",
        )
        unblocked = self._build(
            self.service,
            "client_ban",
            actor_username="admin",
            target_name="vpn-user",
            details="blocked=0",
        )
        assert "Постоянная блокировка" in blocked
        assert self._lines(unblocked)[2].startswith("Разблокировал")

    def test_settings_change_nightly_russian(self):
        text = self._build(
            self.service,
            "settings_change",
            actor_username="Claymore",
            target_name="settings_nightly_update",
            details="enabled=вкл cron=0 4 * * * ttl=180с touch=29с",
        )
        lines = self._lines(text)
        assert len(lines) == 4
        assert "Ночной рестарт" in lines[0]
        assert "включён" in lines[2]
        assert "04:00" in lines[2]
        assert "180" in lines[2]
        assert "29" in lines[2]
        assert "enabled=" not in text
        assert "cron=" not in text

    def test_settings_change_port_russian(self):
        text = self._build(
            self.service,
            "settings_change",
            actor_username="Claymore",
            target_name="settings_port_update",
            details="5050 → 8080",
        )
        lines = self._lines(text)
        assert len(lines) == 4
        assert "Порт панели" in lines[0]
        assert "с 5050 на 8080" in lines[2]

    def test_traffic_limit_block_message(self):
        text = self._build(
            self.service,
            "traffic_limit_block",
            target_name="client-a",
            target_type="wireguard",
            details="limit_bytes=1073741824 consumed_bytes=1610612736 period_days=7",
        )
        assert text is not None
        lines = self._lines(text)
        assert "Блокировка по лимиту трафика" in lines[0]
        assert "превышен лимит трафика" in lines[1]
        assert "WireGuard" in lines[1]
        assert "<code>client-a</code>" in lines[1]
        assert "за неделю" in lines[2]
        assert "1.00 GB" in lines[2]
        assert "1.50 GB" in lines[3]
        assert "Авторазблокировка" in lines[4]

    def test_traffic_limit_unblock_message(self):
        text = self._build(
            self.service,
            "traffic_limit_unblock",
            target_name="client-a",
            target_type="openvpn",
            details="limit_bytes=1048576 consumed_bytes=0 period_days=1",
        )
        assert text is not None
        lines = self._lines(text)
        assert "Авторазблокировка по лимиту трафика" in lines[0]
        assert "новый период учёта" in lines[1]
        assert "OpenVPN" in lines[1]
        assert "Авторазблокировка:" not in text


def _seed_notify_settings(db_session):
    db_session.add(AppSetting(key="telegram_bot_token", value="test-token"))
    db_session.add(AppSetting(key="telegram_notify_enabled", value="true"))
    db_session.commit()


def _make_subscribed_user(username: str, telegram_id: str, events: dict | None = None) -> User:
    user = User(
        username=username,
        password_hash="hash",
        role=UserRole.admin,
        telegram_id=telegram_id,
        tg_notify_events=json.dumps(events or DEFAULT_TG_NOTIFY_EVENTS),
    )
    return user


class TestAdminNotifyDelivery:
    def test_node_context_prepended(self, notify_service):
        text = notify_service._build_text(
            "config_create",
            "admin",
            "client-a",
            "openvpn",
            None,
            None,
            None,
        )
        from app.services.admin_notify import _prepend_node_context

        wrapped = _prepend_node_context(text, node_id=2, node_name="node-1")
        assert wrapped.startswith("📡 Узел: <code>node-1</code> (#2)")
        assert "Создание конфига" in wrapped

    @patch("app.services.admin_notify.send_tg_message")
    @patch("app.services.admin_notify.get_feature_service")
    def test_send_skips_when_feature_disabled(self, mock_feature, mock_send, db_session, notify_service):
        mock_feature.return_value.is_enabled.return_value = False
        _seed_notify_settings(db_session)
        db_session.add(_make_subscribed_user("admin1", "111"))
        db_session.commit()

        notify_service.send(db_session, "login_success", actor_username="admin1")

        mock_send.assert_not_called()

    @patch("app.services.admin_notify.send_tg_message")
    @patch("app.services.admin_notify.get_feature_service")
    def test_send_delivers_to_subscribed_users_only(self, mock_feature, mock_send, db_session, notify_service):
        mock_feature.return_value.is_enabled.return_value = True
        _seed_notify_settings(db_session)
        events = dict(DEFAULT_TG_NOTIFY_EVENTS)
        events["login_success"] = True
        db_session.add(_make_subscribed_user("subscribed", "111", events))
        events_off = dict(DEFAULT_TG_NOTIFY_EVENTS)
        events_off["login_success"] = False
        db_session.add(_make_subscribed_user("unsubscribed", "222", events_off))
        db_session.commit()

        notify_service.send(
            db_session,
            "login_success",
            actor_username="subscribed",
            remote_addr="10.0.0.1",
        )

        mock_send.assert_called_once()
        assert mock_send.call_args[0][1] == "111"

    @patch("app.services.admin_notify.send_tg_message")
    @patch("app.services.admin_notify.get_feature_service")
    def test_send_login_success_wrapper(self, mock_feature, mock_send, db_session, notify_service):
        mock_feature.return_value.is_enabled.return_value = True
        _seed_notify_settings(db_session)
        db_session.add(_make_subscribed_user("admin1", "999"))
        db_session.commit()

        notify_service.send_login_success(
            db_session,
            actor_username="admin1",
            remote_addr="192.0.2.1",
        )

        mock_send.assert_called_once()
        text = mock_send.call_args[0][2]
        assert "Вход в панель" in text
        assert "<code>admin1</code>" in text
