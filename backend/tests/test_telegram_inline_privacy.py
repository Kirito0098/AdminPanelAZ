"""Inline mode must not expose config files/links outside the private chat with the bot."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models import User, UserRole, VpnConfig, VpnType
from app.services.telegram_bot_handlers.inline import build_inline_results


def _ctx(user: User | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        db=MagicMock(),
        user=user,
        telegram_user_id=111,
        bot_token="token",
        mini_app_url="https://example.com/api/tg-mini",
    )


def _user() -> User:
    return User(id=1, username="ivan", password_hash="x", role=UserRole.user, telegram_id="111")


def _config() -> VpnConfig:
    return VpnConfig(id=9, node_id=1, client_name="ivan", vpn_type=VpnType.wireguard, owner_id=1)


def _has_document_or_url(results: list[dict]) -> bool:
    for item in results:
        if item.get("type") == "document":
            return True
        if item.get("document_url"):
            return True
        content = item.get("input_message_content") or {}
        text = str(content.get("message_text") or "")
        if "/api/public/qr-download/" in text:
            return True
    return False


def test_group_chat_type_returns_private_only_article():
    results = build_inline_results(_ctx(_user()), "ivan", chat_type="group")
    assert len(results) == 1
    assert results[0]["id"] == "private_only"
    assert not _has_document_or_url(results)


def test_missing_chat_type_is_blocked():
    results = build_inline_results(_ctx(_user()), "ivan", chat_type=None)
    assert results[0]["id"] == "private_only"
    assert not _has_document_or_url(results)


def test_sender_chat_type_has_no_download_urls():
    with patch(
        "app.services.telegram_bot_handlers.inline.search_user_configs",
        return_value=[_config()],
    ):
        results = build_inline_results(_ctx(_user()), "ivan", chat_type="sender")
    assert any(r.get("type") == "article" and str(r.get("id", "")).startswith("cfg:") for r in results)
    assert not _has_document_or_url(results)


def test_supergroup_channel_and_private_blocked():
    for chat_type in ("supergroup", "channel", "private"):
        results = build_inline_results(_ctx(_user()), "", chat_type=chat_type)
        assert results[0]["id"] == "private_only", chat_type
