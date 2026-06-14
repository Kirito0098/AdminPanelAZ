"""Unit tests for Telegram bot /settings handlers (Phase 3)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth import get_password_hash
from app.models import AppSetting, User, UserActionLog, UserRole
from app.services.telegram_bot_handlers.base import BotContext
from app.services.telegram_bot_handlers import settings_fsm
from app.services.telegram_bot_handlers.settings_admin_notify import handle_settings_admin_notify
from app.services.telegram_bot_handlers.settings_monitor import handle_settings_monitor
from app.services.telegram_bot_handlers.settings_backups import handle_settings_backups
from app.services.telegram_bot_handlers.settings_maintenance import handle_settings_maintenance
from app.services.telegram_bot_handlers.settings_security import handle_settings_security
from app.services.telegram_bot_handlers.settings import (
    handle_settings_callback,
    handle_settings_root,
    handle_settings_text,
    handle_settings_telegram,
)
from tests.conftest import run_async


def _admin_ctx(db, *, telegram_user_id: str = "123456789") -> BotContext:
    admin = db.query(User).filter(User.username == "api_admin").first()
    if admin is None:
        admin = User(
            username="api_admin",
            password_hash=get_password_hash("secret123"),
            role=UserRole.admin,
            is_active=True,
            telegram_id=telegram_user_id,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    else:
        admin.telegram_id = telegram_user_id
        admin.role = UserRole.admin
        db.commit()
    return BotContext(
        db=db,
        bot_token="test-bot-token",
        chat_id=telegram_user_id,
        telegram_user_id=telegram_user_id,
        user=admin,
        mini_app_url="https://panel.example/api/tg-mini",
    )


def _viewer_ctx(db, *, telegram_user_id: str = "999888777") -> BotContext:
    viewer = db.query(User).filter(User.username == "api_viewer").first()
    if viewer is None:
        viewer = User(
            username="api_viewer",
            password_hash=get_password_hash("secret123"),
            role=UserRole.viewer,
            is_active=True,
            telegram_id=telegram_user_id,
        )
        db.add(viewer)
        db.commit()
        db.refresh(viewer)
    else:
        viewer.telegram_id = telegram_user_id
        db.commit()
    return BotContext(
        db=db,
        bot_token="test-bot-token",
        chat_id=telegram_user_id,
        telegram_user_id=telegram_user_id,
        user=viewer,
    )


@pytest.fixture()
def settings_db(api_test_env):
    settings_fsm.clear_all()
    session = api_test_env["session_factory"]()
    try:
        session.add(AppSetting(key="telegram_bot_token", value="123:ABC"))
        session.add(AppSetting(key="telegram_bot_interactive_enabled", value="true"))
        session.add(AppSetting(key="telegram_notify_enabled", value="false"))
        session.commit()
    finally:
        session.close()
    yield api_test_env["session_factory"]
    settings_fsm.clear_all()


def test_settings_root_requires_admin(settings_db):
    session = settings_db()
    try:
        ctx = _viewer_ctx(session)
        with patch(
            "app.services.telegram_bot_handlers.settings.send_message",
            new_callable=AsyncMock,
        ) as send:
            run_async(handle_settings_root(ctx))
        send.assert_awaited_once()
        assert "администратор" in send.call_args.args[2]
    finally:
        session.close()


def test_settings_root_shows_menu(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with patch(
            "app.services.telegram_bot_handlers.settings.send_message",
            new_callable=AsyncMock,
        ) as send:
            run_async(handle_settings_root(ctx))
        send.assert_awaited_once()
        text = send.call_args.args[2]
        assert "Настройки панели" in text
        markup = send.call_args.kwargs.get("reply_markup") or send.call_args.args[3]
        flat = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
        assert "Telegram" in flat
    finally:
        session.close()


def test_toggle_notify_enabled(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with (
            patch(
                "app.services.telegram_bot_handlers.settings.handle_settings_telegram",
                new_callable=AsyncMock,
            ) as refresh,
            patch(
                "app.services.telegram_bot_handlers.settings.edit_message_text",
                new_callable=AsyncMock,
            ),
        ):
            run_async(handle_settings_callback(ctx, "st:tg:ne:1", message_id=42))

        row = session.query(AppSetting).filter(AppSetting.key == "telegram_notify_enabled").first()
        assert row.value == "true"

        log = session.query(UserActionLog).order_by(UserActionLog.id.desc()).first()
        assert log is not None
        assert log.action == "settings_telegram_update"
        assert "source=telegram_bot" in log.details
        assert "notify_enabled" in log.details
        refresh.assert_awaited_once()
    finally:
        session.close()


def test_interactive_off_requires_confirm(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with patch(
            "app.services.telegram_bot_handlers.settings.edit_message_text",
            new_callable=AsyncMock,
        ) as edit:
            run_async(handle_settings_callback(ctx, "st:tg:cfrm:ie:0", message_id=7))
        edit.assert_awaited_once()
        assert "Выключить интерактивный" in edit.call_args.args[3]
        markup = edit.call_args.kwargs.get("reply_markup")
        callbacks = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
        assert "st:tg:do:ie:0" in callbacks
    finally:
        session.close()


def test_token_fsm_confirm_flow(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        settings_fsm.set_pending(ctx.telegram_user_id, "token")
        settings_fsm.set_pending_value(ctx.telegram_user_id, "999:NEWTOKEN")

        with (
            patch(
                "app.services.telegram_bot_handlers.settings.handle_settings_telegram",
                new_callable=AsyncMock,
            ) as refresh,
            patch(
                "app.services.telegram_bot_handlers.settings.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            run_async(handle_settings_callback(ctx, "st:tg:do:token", message_id=None))

        row = session.query(AppSetting).filter(AppSetting.key == "telegram_bot_token").first()
        assert row.value == "999:NEWTOKEN"

        log = session.query(UserActionLog).order_by(UserActionLog.id.desc()).first()
        assert log.action == "settings_telegram_token"
        assert "source=telegram_bot" in log.details
        refresh.assert_awaited_once()
        send.assert_awaited()
    finally:
        session.close()


def test_fsm_username_input(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        settings_fsm.set_pending(ctx.telegram_user_id, "user")

        with (
            patch(
                "app.services.telegram_bot_handlers.settings.handle_settings_telegram",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.telegram_bot_handlers.settings.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            consumed = run_async(handle_settings_text(ctx, "@mybot"))

        assert consumed is True
        row = session.query(AppSetting).filter(AppSetting.key == "telegram_bot_username").first()
        assert row.value == "mybot"
        assert settings_fsm.get_pending(ctx.telegram_user_id) is None
        send.assert_awaited()
    finally:
        session.close()


def test_fsm_age_validation(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        settings_fsm.set_pending(ctx.telegram_user_id, "age")

        with patch(
            "app.services.telegram_bot_handlers.settings.send_message",
            new_callable=AsyncMock,
        ) as send:
            consumed = run_async(handle_settings_text(ctx, "10"))

        assert consumed is True
        assert settings_fsm.get_pending(ctx.telegram_user_id) is not None
        assert "30" in send.call_args.args[2]
    finally:
        session.close()


def test_settings_telegram_menu_content(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with patch(
            "app.services.telegram_bot_handlers.settings.send_message",
            new_callable=AsyncMock,
        ) as send:
            run_async(handle_settings_telegram(ctx))
        text = send.call_args.args[2]
        assert "Telegram — настройки" in text
        assert "Max auth age" in text
    finally:
        session.close()


def test_admin_notify_menu(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with patch(
            "app.services.telegram_bot_handlers.settings.send_message",
            new_callable=AsyncMock,
        ) as send:
            run_async(handle_settings_admin_notify(ctx))
        text = send.call_args.args[2]
        assert "Уведомления администратору" in text
        assert "123456789" in text
        markup = send.call_args.kwargs.get("reply_markup") or send.call_args.args[3]
        flat = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
        assert "st:an:e:login_success" in flat
    finally:
        session.close()


def test_toggle_admin_notify_event(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with (
            patch(
                "app.services.telegram_bot_handlers.settings_admin_notify.handle_settings_admin_notify",
                new_callable=AsyncMock,
            ) as refresh,
            patch(
                "app.services.telegram_bot_handlers.settings.edit_message_text",
                new_callable=AsyncMock,
            ),
        ):
            run_async(handle_settings_callback(ctx, "st:an:e:login_success", message_id=5))

        admin = session.query(User).filter(User.username == "api_admin").first()
        merged = admin.merged_tg_notify_events()
        assert merged.get("login_success") is False

        log = session.query(UserActionLog).order_by(UserActionLog.id.desc()).first()
        assert log.action == "settings_admin_notify_update"
        assert "source=telegram_bot" in log.details
        assert "login_success" in log.details
        refresh.assert_awaited_once()
    finally:
        session.close()


def test_admin_notify_set_my_id(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session, telegram_user_id="555000111")
        ctx.user.telegram_id = None
        session.commit()

        with (
            patch(
                "app.services.telegram_bot_handlers.settings_admin_notify.handle_settings_admin_notify",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_admin_notify.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            run_async(handle_settings_callback(ctx, "st:an:me", message_id=None))

        admin = session.query(User).filter(User.username == "api_admin").first()
        assert admin.telegram_id == "555000111"
        send.assert_awaited()
    finally:
        session.close()


def test_admin_notify_fsm_telegram_id(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        settings_fsm.set_pending(ctx.telegram_user_id, "an_tgid")

        with (
            patch(
                "app.services.telegram_bot_handlers.settings_admin_notify.handle_settings_admin_notify",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_admin_notify.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            consumed = run_async(handle_settings_text(ctx, "888777666"))

        assert consumed is True
        admin = session.query(User).filter(User.username == "api_admin").first()
        assert admin.telegram_id == "888777666"
        assert settings_fsm.get_pending(ctx.telegram_user_id) is None
        send.assert_awaited()
    finally:
        session.close()


def test_monitor_menu(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with patch(
            "app.services.telegram_bot_handlers.settings.send_message",
            new_callable=AsyncMock,
        ) as send:
            run_async(handle_settings_monitor(ctx))
        text = send.call_args.args[2]
        assert "Мониторинг CPU/RAM" in text
        assert "Порог CPU" in text
        markup = send.call_args.kwargs.get("reply_markup") or send.call_args.args[3]
        flat = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
        assert "st:mon:ask:cpu" in flat
    finally:
        session.close()


def test_monitor_fsm_cpu_threshold(settings_db, monkeypatch):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        settings_fsm.set_pending(ctx.telegram_user_id, "mon_cpu")

        with (
            patch(
                "app.services.telegram_bot_handlers.settings_monitor.handle_settings_monitor",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_monitor.send_message",
                new_callable=AsyncMock,
            ) as send,
            patch("app.routers.settings.EnvFileService") as env_cls,
        ):
            env_cls.return_value.set_env_value = MagicMock()
            monkeypatch.setenv("MONITOR_CPU_THRESHOLD", "90")
            consumed = run_async(handle_settings_text(ctx, "85"))

        assert consumed is True
        log = session.query(UserActionLog).order_by(UserActionLog.id.desc()).first()
        assert log.action == "settings_monitor_update"
        assert "source=telegram_bot" in log.details
        assert "mon_cpu" in log.details
        assert settings_fsm.get_pending(ctx.telegram_user_id) is None
        send.assert_awaited()
    finally:
        session.close()


def test_monitor_fsm_invalid_value(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        settings_fsm.set_pending(ctx.telegram_user_id, "mon_ram")

        with patch(
            "app.services.telegram_bot_handlers.settings_monitor.send_message",
            new_callable=AsyncMock,
        ) as send:
            consumed = run_async(handle_settings_text(ctx, "abc"))

        assert consumed is True
        assert settings_fsm.get_pending(ctx.telegram_user_id) is not None
        assert "1" in send.call_args.args[2]
    finally:
        session.close()


def test_backups_menu(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with (
            patch(
                "app.services.telegram_bot_handlers.settings_backups._list_backups",
                return_value=[],
            ),
            patch(
                "app.services.telegram_bot_handlers.settings.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            run_async(handle_settings_backups(ctx))
        text = send.call_args.args[2]
        assert "Бэкапы" in text
        markup = send.call_args.kwargs.get("reply_markup") or send.call_args.args[3]
        flat = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
        assert "st:bk:auto:1" in flat
        assert "st:bk:test" in flat
    finally:
        session.close()


def test_toggle_auto_backup(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with (
            patch(
                "app.services.telegram_bot_handlers.settings_backups._list_backups",
                return_value=[],
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_backups.handle_settings_backups",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.telegram_bot_handlers.settings.edit_message_text",
                new_callable=AsyncMock,
            ),
        ):
            run_async(handle_settings_callback(ctx, "st:bk:auto:1", message_id=3))

        row = session.query(AppSetting).filter(AppSetting.key == "backup_auto_enabled").first()
        assert row.value == "true"
        log = session.query(UserActionLog).order_by(UserActionLog.id.desc()).first()
        assert log.action == "settings_backup_update"
        assert "source=telegram_bot" in log.details
    finally:
        session.close()


def test_backups_fsm_retention(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        settings_fsm.set_pending(ctx.telegram_user_id, "bk_ret")

        with (
            patch(
                "app.services.telegram_bot_handlers.settings_backups._list_backups",
                return_value=[],
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_backups.handle_settings_backups",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_backups.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            consumed = run_async(handle_settings_text(ctx, "10"))

        assert consumed is True
        row = session.query(AppSetting).filter(AppSetting.key == "backup_retention").first()
        assert row.value == "10"
        assert settings_fsm.get_pending(ctx.telegram_user_id) is None
        send.assert_awaited()
    finally:
        session.close()


def test_maintenance_menu(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with (
            patch(
                "app.services.telegram_bot_handlers.settings_maintenance._antizapret_path",
                return_value="/opt/antizapret",
            ),
            patch(
                "app.services.telegram_bot_handlers.settings.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            run_async(handle_settings_maintenance(ctx))
        text = send.call_args.args[2]
        assert "Обслуживание" in text
        assert "/opt/antizapret" in text
        markup = send.call_args.kwargs.get("reply_markup") or send.call_args.args[3]
        flat = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
        assert "st:mnt:cfrm:doall" in flat
    finally:
        session.close()


def test_maintenance_doall_confirm(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with (
            patch(
                "app.routers.maintenance.run_doall",
                return_value={"message": "doall в очереди", "task_id": 1},
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_maintenance.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            run_async(handle_settings_callback(ctx, "st:mnt:do:doall", message_id=None))

        log = session.query(UserActionLog).order_by(UserActionLog.id.desc()).first()
        assert log.action == "settings_run_doall"
        assert "source=telegram_bot" in log.details
        send.assert_awaited()
    finally:
        session.close()


def test_maintenance_restart_service(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with (
            patch(
                "app.routers.maintenance.restart_service",
            ) as restart,
            patch(
                "app.services.telegram_bot_handlers.settings_maintenance.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            from app.schemas import MessageResponse

            restart.return_value = MessageResponse(message="Служба перезапущена")
            run_async(handle_settings_callback(ctx, "st:mnt:do:rst:5", message_id=None))

        restart.assert_called_once()
        assert restart.call_args.args[0].service_name == "wg-quick@vpn"
        log = session.query(UserActionLog).order_by(UserActionLog.id.desc()).first()
        assert log.action == "settings_restart_service"
        send.assert_awaited()
    finally:
        session.close()


def test_security_menu(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        sample = {
            "ip_restriction_enabled": True,
            "allowed_ips": ["10.0.0.1"],
            "whitelist_firewall_active": False,
            "block_scanners": True,
            "temp_whitelist": [],
        }
        with (
            patch(
                "app.services.telegram_bot_handlers.settings_security._get_security",
                return_value=sample,
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_security._get_scanner_bans",
                return_value=[],
            ),
            patch(
                "app.services.telegram_bot_handlers.settings.send_message",
                new_callable=AsyncMock,
            ) as send,
        ):
            run_async(handle_settings_security(ctx))
        text = send.call_args.args[2]
        assert "Безопасность" in text
        assert "10.0.0.1" in text
    finally:
        session.close()


def test_toggle_ip_restriction(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        with (
            patch(
                "app.services.telegram_bot_handlers.settings_security._get_security",
                return_value={
                    "ip_restriction_enabled": False,
                    "allowed_ips": [],
                    "whitelist_firewall_active": False,
                    "block_scanners": False,
                    "temp_whitelist": [],
                },
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_security._get_scanner_bans",
                return_value=[],
            ),
            patch(
                "app.routers.security.update_security",
                return_value={},
            ),
            patch(
                "app.services.telegram_bot_handlers.settings_security.handle_settings_security",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.telegram_bot_handlers.settings.edit_message_text",
                new_callable=AsyncMock,
            ),
        ):
            run_async(handle_settings_callback(ctx, "st:sec:ip:1", message_id=2))

        log = session.query(UserActionLog).order_by(UserActionLog.id.desc()).first()
        assert log.action == "settings_security_update"
        assert "source=telegram_bot" in log.details
    finally:
        session.close()


def test_security_temp_ip_fsm(settings_db):
    session = settings_db()
    try:
        ctx = _admin_ctx(session)
        settings_fsm.set_pending(ctx.telegram_user_id, "sec_tmp_ip")

        with patch(
            "app.services.telegram_bot_handlers.settings_security.send_message",
            new_callable=AsyncMock,
        ) as send:
            consumed = run_async(handle_settings_text(ctx, "203.0.113.50"))

        assert consumed is True
        pending = settings_fsm.get_pending(ctx.telegram_user_id)
        assert pending is not None
        assert pending.value == "203.0.113.50"
        markup = send.call_args.kwargs.get("reply_markup") or send.call_args.args[3]
        flat = [btn["callback_data"] for row in markup["inline_keyboard"] for btn in row]
        assert "st:sec:tmp:12" in flat
    finally:
        session.close()
