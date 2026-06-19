"""Plugin registry and notify backend hook tests."""

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSetting, DEFAULT_TG_NOTIFY_EVENTS, User, UserRole
from app.services.admin_notify import AdminNotifyService
from app.services.notify_backend_example import example_logging_notify_backend
from app.services.notify_backends import (
    NOTIFY_SEND_HOOK,
    dispatch_admin_notify,
    list_notify_backends,
    register_notify_backend,
)
from app.services.plugin_registry import HookRegistry, hook_registry


@pytest.fixture()
def isolated_registry():
    saved = dict(hook_registry._hooks)
    hook_registry.clear()
    yield hook_registry
    hook_registry._hooks.clear()
    hook_registry._hooks.update(saved)


class TestNotifyBackends:
    def test_list_includes_default_telegram_backend(self):
        assert "telegram" in list_notify_backends()

    def test_register_example_backend(self, isolated_registry: HookRegistry):
        isolated_registry.register(NOTIFY_SEND_HOOK, "telegram", lambda **_: None)
        register_notify_backend("example_logging", example_logging_notify_backend)
        assert list_notify_backends() == ["telegram", "example_logging"]

    def test_dispatch_calls_registered_backends(self, isolated_registry: HookRegistry):
        received: list[dict] = []

        def capture(**kwargs):
            received.append(kwargs)

        isolated_registry.register(NOTIFY_SEND_HOOK, "capture", capture)
        dispatch_admin_notify(
            MagicMock(),
            event_type="login_success",
            text="hello",
            recipients=[MagicMock(telegram_id="42")],
            bot_token="token",
        )
        assert len(received) == 1
        assert received[0]["event_type"] == "login_success"
        assert received[0]["text"] == "hello"
        assert received[0]["bot_token"] == "token"


class TestAdminNotifyViaRegistry:
    @pytest.fixture()
    def db_session(self, tmp_path):
        db_path = tmp_path / "plugin_notify.db"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    @patch("app.services.admin_notify.send_tg_message")
    @patch("app.services.admin_notify.get_feature_service")
    def test_send_uses_telegram_backend(self, mock_feature, mock_send, db_session):
        mock_feature.return_value.is_enabled.return_value = True
        db_session.add(AppSetting(key="telegram_notify_enabled", value="true"))
        db_session.add(AppSetting(key="telegram_bot_token", value="test-token"))
        events = dict(DEFAULT_TG_NOTIFY_EVENTS)
        events["login_success"] = True
        db_session.add(
            User(
                username="admin1",
                password_hash="hash",
                role=UserRole.admin,
                telegram_id="111",
                tg_notify_events=json.dumps(events),
            )
        )
        db_session.commit()

        service = AdminNotifyService(logger_instance=MagicMock())
        service.send(db_session, "login_success", actor_username="admin1")

        mock_send.assert_called_once()
        assert mock_send.call_args[0][:2] == ("test-token", "111")

    @patch("app.services.admin_notify.send_tg_message")
    @patch("app.services.admin_notify.get_feature_service")
    def test_example_backend_runs_alongside_telegram(self, mock_feature, mock_send, db_session):
        mock_feature.return_value.is_enabled.return_value = True
        db_session.add(AppSetting(key="telegram_notify_enabled", value="true"))
        db_session.add(AppSetting(key="telegram_bot_token", value="test-token"))
        events = dict(DEFAULT_TG_NOTIFY_EVENTS)
        events["login_success"] = True
        db_session.add(
            User(
                username="admin1",
                password_hash="hash",
                role=UserRole.admin,
                telegram_id="111",
                tg_notify_events=json.dumps(events),
            )
        )
        db_session.commit()

        log_calls: list[tuple] = []

        def tracking_example(**kwargs):
            log_calls.append((kwargs["event_type"], len(kwargs["recipients"])))

        register_notify_backend("example_logging", tracking_example)
        try:
            service = AdminNotifyService(logger_instance=MagicMock())
            service.send(db_session, "login_success", actor_username="admin1")
        finally:
            hook_registry._hooks[NOTIFY_SEND_HOOK] = [
                (name, handler)
                for name, handler in hook_registry._hooks.get(NOTIFY_SEND_HOOK, [])
                if name != "example_logging"
            ]

        mock_send.assert_called_once()
        assert log_calls == [("login_success", 1)]
