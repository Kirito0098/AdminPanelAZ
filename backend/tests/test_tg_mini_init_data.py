"""Telegram Mini App initData verification — ported from AdminAntizapret."""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

import pytest

from app.routers.tg_mini import _verify_telegram_init_data


def _sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    body = dict(fields)
    data_check_string = "\n".join(f"{k}={body[k]}" for k in sorted(body.keys()))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    digest = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    out = dict(body)
    out["hash"] = digest
    return urlencode(out)


def test_verify_accepts_valid_init_data() -> None:
    token = "test-tg-mini-verify-token"
    auth_date = str(int(time.time()))
    user_json = '{"id":777001,"first_name":"Ada","last_name":"Lovelace","username":"ada"}'
    raw = _sign_init_data(
        {"auth_date": auth_date, "query_id": "AAQxtest", "user": user_json},
        token,
    )
    payload = _verify_telegram_init_data(raw, token)
    assert payload["id"] == 777001
    assert payload["username"] == "ada"


def test_verify_rejects_bad_hash() -> None:
    token = "test-tg-mini-bad-hash-token"
    auth_date = str(int(time.time()))
    user_json = '{"id":1,"first_name":"X"}'
    raw = _sign_init_data(
        {"auth_date": auth_date, "query_id": "Q", "user": user_json},
        token,
    )
    tampered = raw.replace("hash=", "hash=0")
    with pytest.raises(ValueError, match="подпись|hash|Неверная"):
        _verify_telegram_init_data(tampered, token)


def test_verify_rejects_missing_hash() -> None:
    with pytest.raises(ValueError, match="hash"):
        _verify_telegram_init_data("auth_date=1&user=%7B%7D", "token")
