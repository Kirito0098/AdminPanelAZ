"""Tests for refresh-token cookie Secure flag on HTTP vs HTTPS."""

from unittest.mock import MagicMock

from app.config import Settings
from app.services.auth_cookies import client_request_is_https, refresh_token_cookie_secure


def _request(*, scheme: str, forwarded: str | None = None) -> MagicMock:
    req = MagicMock()
    req.url.scheme = scheme
    headers = {}
    if forwarded is not None:
        headers["x-forwarded-proto"] = forwarded
    req.headers.get.side_effect = lambda key, default=None: headers.get(key.lower(), headers.get(key, default))
    return req


def test_http_request_never_sets_secure_even_in_production():
    settings = Settings(
        app_env="production",
        refresh_token_cookie_secure=True,
        enforce_https=True,
        behind_nginx=True,
    )
    assert refresh_token_cookie_secure(settings, _request(scheme="http")) is False


def test_https_request_sets_secure():
    settings = Settings(app_env="development", refresh_token_cookie_secure=False)
    assert refresh_token_cookie_secure(settings, _request(scheme="https")) is True


def test_forwarded_proto_https_sets_secure():
    settings = Settings(app_env="development", refresh_token_cookie_secure=False)
    assert (
        refresh_token_cookie_secure(
            settings,
            _request(scheme="http", forwarded="https"),
        )
        is True
    )


def test_no_request_falls_back_to_behind_nginx():
    settings = Settings(
        app_env="production",
        refresh_token_cookie_secure=False,
        enforce_https=False,
        behind_nginx=True,
    )
    assert refresh_token_cookie_secure(settings, None) is True


def test_no_request_production_alone_is_not_secure():
    settings = Settings(
        app_env="production",
        refresh_token_cookie_secure=False,
        enforce_https=False,
        behind_nginx=False,
    )
    assert refresh_token_cookie_secure(settings, None) is False


def test_client_request_is_https_helpers():
    assert client_request_is_https(None) is None
    assert client_request_is_https(_request(scheme="https")) is True
    assert client_request_is_https(_request(scheme="http")) is False
