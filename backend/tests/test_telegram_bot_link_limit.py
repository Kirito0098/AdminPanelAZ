"""Bot /link reuses the login limiter, keyed per Telegram user id."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.services.auth_rate_limit import AuthRateLimitService
from app.services.telegram_bot_handlers import link, start

MAX_ATTEMPTS = 3
LOCKED_MESSAGE = "Слишком много попыток привязки. Повторите позже."
GOOD_CODE = "good"


@pytest.fixture(autouse=True)
def limiter(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "auth_rate_limit_backend", "memory")
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", MAX_ATTEMPTS)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 300)
    monkeypatch.setattr(link, "auth_rate_limit_service", AuthRateLimitService())


@pytest.fixture
def bot(monkeypatch):
    state = SimpleNamespace(sent=[], redeemed=[])

    async def fake_send_message(_token, _chat, text, **_kw):
        state.sent.append(text)

    def fake_redeem(_db, code, telegram_id):
        state.redeemed.append((code, telegram_id))
        if code == GOOD_CODE:
            return True, "linked", SimpleNamespace(id=1, username="carol")
        return False, "Код не найден или истёк.", None

    async def fake_start(_ctx):
        return None

    monkeypatch.setattr(link, "send_message", fake_send_message)
    monkeypatch.setattr(link, "redeem_link_code", fake_redeem)
    monkeypatch.setattr(link, "log_action", lambda *_a, **_k: None)
    monkeypatch.setattr(start, "handle_start", fake_start)
    return state


def _link(code: str, telegram_user_id: str = "100") -> None:
    ctx = SimpleNamespace(db=None, bot_token="bot", chat_id=1, telegram_user_id=telegram_user_id, user=None)
    asyncio.run(link.handle_link(ctx, code))


def test_link_locks_after_repeated_wrong_codes(bot):
    for _ in range(MAX_ATTEMPTS):
        _link("wrong")

    _link(GOOD_CODE)

    assert bot.sent[-1] == LOCKED_MESSAGE
    assert len(bot.redeemed) == MAX_ATTEMPTS


def test_link_lock_is_per_telegram_user(bot):
    for _ in range(MAX_ATTEMPTS):
        _link("wrong", telegram_user_id="100")

    _link(GOOD_CODE, telegram_user_id="200")

    assert bot.sent[-1] == "linked"


def test_successful_link_resets_counter(bot):
    for _ in range(MAX_ATTEMPTS - 1):
        _link("wrong")
    _link(GOOD_CODE)

    for _ in range(MAX_ATTEMPTS - 1):
        _link("wrong")

    assert LOCKED_MESSAGE not in bot.sent
    assert len(bot.redeemed) == 2 * MAX_ATTEMPTS - 1
