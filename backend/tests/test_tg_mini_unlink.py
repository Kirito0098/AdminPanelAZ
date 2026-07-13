"""Mini App must revoke access immediately when Telegram is unlinked."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth import get_tg_mini_user, require_tg_mini_admin
from app.models import UserRole
from app.routers.tg_mini import TelegramAuthRequest, tg_auth


def _user(*, username: str = "alice", role: UserRole = UserRole.user, telegram_id: str | None = "12345"):
    user = MagicMock()
    user.id = 1
    user.username = username
    user.role = role
    user.telegram_id = telegram_id
    user.is_active = True
    return user


def test_get_tg_mini_user_rejects_unlinked():
    with pytest.raises(HTTPException) as exc:
        get_tg_mini_user(current_user=_user(telegram_id=None))
    assert exc.value.status_code == 401
    assert "не привязан" in exc.value.detail


def test_get_tg_mini_user_rejects_blank_telegram_id():
    with pytest.raises(HTTPException) as exc:
        get_tg_mini_user(current_user=_user(telegram_id="   "))
    assert exc.value.status_code == 401


def test_get_tg_mini_user_allows_linked():
    user = _user(telegram_id="999")
    assert get_tg_mini_user(current_user=user) is user


def test_require_tg_mini_admin_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        require_tg_mini_admin(current_user=_user(role=UserRole.user, telegram_id="1"))
    assert exc.value.status_code == 403


def test_require_tg_mini_admin_allows_linked_admin():
    admin = _user(username="admin", role=UserRole.admin, telegram_id="1")
    assert require_tg_mini_admin(current_user=admin) is admin


def test_tg_auth_does_not_auto_relink_tg_username(monkeypatch):
    """Unlinked tg_<id> accounts must not get telegram_id restored on Mini App auth."""
    tg_id = "424242"
    orphan = _user(username=f"tg_{tg_id}", telegram_id=None)

    db = MagicMock()
    query = MagicMock()
    # First filter(telegram_id == ...) → no match; must not fall back to username lookup.
    query.filter.return_value.first.return_value = None
    db.query.return_value = query

    monkeypatch.setattr("app.routers.tg_mini._get_bot_token", lambda _db: "bot:token")
    monkeypatch.setattr("app.routers.tg_mini._get_setting", lambda _db, _key, default="": "300")
    monkeypatch.setattr(
        "app.routers.tg_mini._verify_telegram_init_data",
        lambda *_a, **_k: {"id": int(tg_id)},
    )
    notify = MagicMock()
    monkeypatch.setattr("app.routers.tg_mini.admin_notify_service.send_tg_login_unlinked", notify)
    monkeypatch.setattr(
        "app.routers.tg_mini.ip_restriction_service.get_client_ip",
        lambda _req: "127.0.0.1",
    )
    monkeypatch.setattr("app.routers.tg_mini.get_client_timezone_from_request", lambda _req: None)

    request = MagicMock()
    payload = TelegramAuthRequest(init_data="user=%7B%22id%22%3A424242%7D&hash=x")

    with pytest.raises(HTTPException) as exc:
        tg_auth(payload=payload, request=request, db=db)

    assert exc.value.status_code == 401
    assert "не привязан" in exc.value.detail
    assert orphan.telegram_id is None
    db.commit.assert_not_called()
    notify.assert_called_once()


def test_tg_auth_issues_token_when_linked(monkeypatch):
    tg_id = "555"
    linked = _user(username="bob", telegram_id=tg_id)

    db = MagicMock()
    query = MagicMock()
    query.filter.return_value.first.return_value = linked
    db.query.return_value = query

    monkeypatch.setattr("app.routers.tg_mini._get_bot_token", lambda _db: "bot:token")
    monkeypatch.setattr("app.routers.tg_mini._get_setting", lambda _db, _key, default="": "300")
    monkeypatch.setattr(
        "app.routers.tg_mini._verify_telegram_init_data",
        lambda *_a, **_k: {"id": int(tg_id)},
    )
    monkeypatch.setattr("app.routers.tg_mini.create_access_token", lambda data: "jwt-token")

    request = MagicMock()
    payload = TelegramAuthRequest(init_data="user=%7B%22id%22%3A555%7D&hash=x")

    result = tg_auth(payload=payload, request=request, db=db)

    assert result["access_token"] == "jwt-token"
    assert result["telegram_id"] == tg_id
    db.commit.assert_not_called()
