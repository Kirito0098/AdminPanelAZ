import types

import pytest

from app.services import bulk_user_notify as mod


def _user(user_id: int, username: str, telegram_id: str | None):
    return types.SimpleNamespace(id=user_id, username=username, telegram_id=telegram_id)


def test_run_bulk_notify_skips_users_without_telegram(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(
        mod,
        "send_bulk_user_notify",
        lambda **kwargs: sent.append(kwargs) or "sent",
    )
    users = [_user(1, "a", "111"), _user(2, "b", None)]
    stats = mod._run_bulk_notify(users, "hi", "token", lambda *_args: None)

    assert stats["delivered"] == 1
    assert stats["no_telegram"] == 1
    assert len(sent) == 1
    assert sent[0]["telegram_id"] == "111"


def test_run_bulk_notify_403_is_undelivered(monkeypatch):
    monkeypatch.setattr(mod, "send_bulk_user_notify", lambda **kwargs: "undelivered")
    stats = mod._run_bulk_notify([_user(1, "a", "111")], "hi", "token", lambda *_args: None)

    assert stats["undelivered"] == 1
    assert stats["delivered"] == 0


def test_bulk_notify_request_rejects_empty_text():
    from app.schemas import BulkNotifyRequest

    with pytest.raises(ValueError):
        BulkNotifyRequest(user_ids=[1], text="")
