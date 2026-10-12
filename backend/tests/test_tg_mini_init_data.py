"""Mini App initData signature check."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse

import pytest

from app.routers.tg_mini import helpers

BOT_TOKEN = "123:abc"


def _signed(fields: dict[str, str]) -> str:
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode({**fields, "hash": digest})


def _fields() -> dict[str, str]:
    return {"auth_date": str(int(time.time())), "user": json.dumps({"id": 555})}


def test_valid_init_data_returns_user():
    assert helpers._verify_telegram_init_data(_signed(_fields()), BOT_TOKEN) == {"id": 555}


def test_tampered_init_data_rejected():
    tampered = _signed(_fields()).replace("555", "556")
    with pytest.raises(ValueError, match="подпись"):
        helpers._verify_telegram_init_data(tampered, BOT_TOKEN)


def test_signature_compared_in_constant_time(monkeypatch):
    calls: list[tuple[str, str]] = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(helpers.hmac, "compare_digest", spy)

    helpers._verify_telegram_init_data(_signed(_fields()), BOT_TOKEN)

    assert len(calls) == 1
