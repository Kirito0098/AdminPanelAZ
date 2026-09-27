"""Telegram admin notifications are sent with parse_mode=HTML: user-controlled values must be escaped."""

from app.services.admin_notify import AdminNotifyService, _preview_owner_reminder_text
from app.services.user_reminder_service import REMINDER_ACCESS, _build_owner_message

_PAYLOAD = '<a href="https://evil.example">click</a>&'
_ESCAPED = "&lt;a href=&quot;https://evil.example&quot;&gt;click&lt;/a&gt;&amp;"


def _build(event_type: str, **kwargs) -> str:
    params = {
        "actor_username": None,
        "target_name": None,
        "target_type": None,
        "remote_addr": None,
        "details": None,
    }
    params.update(kwargs)
    text = AdminNotifyService()._build_text(event_type, **params)
    assert text is not None
    return text


def test_login_failed_escapes_username():
    text = _build("login_failed", actor_username=_PAYLOAD, remote_addr="203.0.113.5")
    assert _ESCAPED in text
    assert "<a href" not in text


def test_login_failed_escapes_unrecognized_user_agent():
    text = _build("login_failed", actor_username="bob", user_agent=_PAYLOAD)
    assert _ESCAPED in text
    assert "<a href" not in text


def test_settings_change_escapes_user_supplied_names():
    text = _build(
        "settings_change",
        actor_username="admin",
        target_name="settings_backup_upload",
        subject_name=_PAYLOAD,
    )
    assert "<a href" not in text
    assert _ESCAPED in text


def test_plain_text_details_are_escaped():
    text = _build("node_offline", details="connect failed: <urlopen error [Errno 111]>", node_name="n1", node_id=1)
    assert "&lt;urlopen error [Errno 111]&gt;" in text


def test_user_create_details_are_escaped():
    text = _build("user_create", actor_username="admin", target_name="alice", details=_PAYLOAD)
    assert _ESCAPED in text


def test_client_and_node_names_are_escaped():
    text = _build(
        "config_create",
        actor_username="admin",
        target_name="<b>c1</b>",
        target_type="wireguard",
        node_name="<i>node</i>",
        node_id=3,
    )
    assert "&lt;b&gt;c1&lt;/b&gt;" in text
    assert "&lt;i&gt;node&lt;/i&gt;" in text


def test_reminder_details_keep_server_generated_markup():
    details = "Доступ до <code>2026-07-10</code>, осталось <b>5</b> дн."
    admin_text = _build("user_access_expiry_reminder", subject_name="bob", details=details)
    owner_text = _build_owner_message(REMINDER_ACCESS, details)
    for text in (admin_text, owner_text):
        assert "<code>2026-07-10</code>" in text
        assert "<b>5</b>" in text


def test_owner_reminder_preview_keeps_markup():
    text = _preview_owner_reminder_text("access_expiry_reminder")
    assert text is not None
    assert "<code>2026-07-10</code>" in text
