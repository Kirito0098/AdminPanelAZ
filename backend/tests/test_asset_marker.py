"""Asset marker: a signed expiry that lets a signed-in browser download login-only frontend chunks."""

import pytest

from app.services.asset_marker import asset_marker_valid, issue_asset_marker

KEY = "k" * 32


def test_fresh_marker_is_valid():
    assert asset_marker_valid(KEY, issue_asset_marker(KEY, 60, now=1000), now=1059)


def test_expired_marker_is_rejected():
    assert not asset_marker_valid(KEY, issue_asset_marker(KEY, 60, now=1000), now=1060)


def test_marker_signed_with_another_key_is_rejected():
    assert not asset_marker_valid(KEY, issue_asset_marker("other-key" * 4, 60, now=1000), now=1001)


def test_extending_the_expiry_breaks_the_signature():
    expires, _, signature = issue_asset_marker(KEY, 60, now=1000).partition(".")
    assert not asset_marker_valid(KEY, f"{int(expires) + 3600}.{signature}", now=1001)


@pytest.mark.parametrize(
    "value",
    [None, "", "abc", "1060", "1060.", ".signature", "²⁰⁶⁰.signature", "9999999999.подпись"],
)
def test_malformed_marker_is_rejected(value):
    assert not asset_marker_valid(KEY, value, now=1001)
