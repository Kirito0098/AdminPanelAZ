import pytest

from app.config import Settings
from app.services.panel_paths import (
    AccessPathError,
    access_path,
    api_prefix,
    append_access_path_to_url_root,
    auth_cookie_path,
    get_ip_blocked_paths,
    normalize_access_path,
    strip_access_path,
    with_access_path,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        (None, ""),
        ("/", ""),
        ("panel", "/panel"),
        ("/panel", "/panel"),
        ("/panel/", "/panel"),
        ("/my-panel", "/my-panel"),
    ],
)
def test_normalize_access_path_valid(raw, expected):
    assert normalize_access_path(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "/api",
        "/api/foo",
        "/assets",
        "/.well-known",
        "/../panel",
        "/panel/../admin",
        "/bad path",
        "/панель",
    ],
)
def test_normalize_access_path_invalid(raw):
    with pytest.raises(AccessPathError):
        normalize_access_path(raw)


def test_settings_access_path_validator():
    settings = Settings(access_path="/panel/")
    assert settings.access_path == "/panel"


def test_helpers_with_prefix():
    settings = Settings(access_path="/panel")
    assert access_path(settings) == "/panel"
    assert api_prefix(settings) == "/panel/api"
    assert auth_cookie_path(settings) == "/panel/api/auth"
    assert with_access_path(settings, "/login") == "/panel/login"
    assert with_access_path(settings, "/") == "/panel/"
    assert append_access_path_to_url_root("https://example.com/", settings) == "https://example.com/panel/"


def test_strip_access_path():
    settings = Settings(access_path="/panel")
    assert strip_access_path("/panel/api/health", settings) == "/api/health"
    assert strip_access_path("/panel/", settings) == "/"
    assert strip_access_path("/api/health", Settings(access_path="")) == "/api/health"


def test_get_ip_blocked_paths():
    settings = Settings(access_path="/panel")
    paths = get_ip_blocked_paths(settings)
    assert "/panel/ip-blocked" in paths
    assert "/panel/api/ip-blocked/ping" in paths


def test_helpers_without_prefix():
    settings = Settings(access_path="")
    assert access_path(settings) == ""
    assert api_prefix(settings) == "/api"
    assert auth_cookie_path(settings) == "/api/auth"
    assert with_access_path(settings, "/login") == "/login"
    assert append_access_path_to_url_root("https://example.com/", settings) == "https://example.com/"
