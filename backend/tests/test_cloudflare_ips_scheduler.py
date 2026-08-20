from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.services import cloudflare_ips_scheduler as scheduler
from app.services.worker_lifecycle import should_start_cloudflare_ips_scheduler


def test_should_refresh_skips_when_proxy_disabled():
    assert (
        scheduler.should_refresh_cloudflare_ips(
            enabled=False,
            auto_update=True,
            interval_days=7,
            last_success_at=None,
        )
        is False
    )


def test_should_refresh_skips_when_auto_update_disabled():
    assert (
        scheduler.should_refresh_cloudflare_ips(
            enabled=True,
            auto_update=False,
            interval_days=7,
            last_success_at=None,
        )
        is False
    )


def test_should_refresh_skips_when_interval_not_elapsed():
    now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    last = (now - timedelta(days=2)).isoformat()
    assert (
        scheduler.should_refresh_cloudflare_ips(
            enabled=True,
            auto_update=True,
            interval_days=7,
            last_success_at=last,
            now=now,
        )
        is False
    )


def test_should_refresh_runs_when_never_succeeded():
    assert (
        scheduler.should_refresh_cloudflare_ips(
            enabled=True,
            auto_update=True,
            interval_days=7,
            last_success_at=None,
        )
        is True
    )


def test_should_refresh_runs_when_interval_elapsed():
    now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    last = (now - timedelta(days=8)).isoformat()
    assert (
        scheduler.should_refresh_cloudflare_ips(
            enabled=True,
            auto_update=True,
            interval_days=7,
            last_success_at=last,
            now=now,
        )
        is True
    )


def test_should_run_treats_invalid_timestamp_as_due():
    now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    assert scheduler.should_run_interval("", 7, now=now) is True
    assert scheduler.should_run_interval("not-a-date", 7, now=now) is True


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("true", True),
        ("false", False),
    ],
)
def test_should_start_cloudflare_ips_scheduler(monkeypatch, env_value, expected):
    monkeypatch.setenv("CLOUDFLARE_PROXY_ENABLED", env_value)
    get_settings.cache_clear()
    try:
        assert should_start_cloudflare_ips_scheduler() is expected
    finally:
        get_settings.cache_clear()
