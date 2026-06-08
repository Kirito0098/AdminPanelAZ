"""Tests for nightly idle restart worker."""

from datetime import datetime, timezone
from unittest.mock import patch

from app.config import Settings
from app.models import ActiveWebSession
from app.services.nightly_idle_restart_worker import cron_matches_now, run_nightly_idle_restart_once


def test_cron_matches_now_default_schedule():
    dt = datetime(2026, 6, 8, 4, 0, tzinfo=timezone.utc)
    assert cron_matches_now("0 4 * * *", dt) is True
    assert cron_matches_now("0 4 * * *", dt.replace(minute=1)) is False


def test_nightly_restart_skips_when_disabled():
    with patch("app.services.nightly_idle_restart_worker.get_settings") as mock_settings:
        mock_settings.return_value = Settings(nightly_idle_restart_enabled=False)
        result = run_nightly_idle_restart_once()
    assert result["status"] == "disabled"


def test_nightly_restart_skips_with_active_sessions(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        db.add(
            ActiveWebSession(
                session_id="active1",
                username="api_admin",
                created_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
            )
        )
        db.commit()
    finally:
        db.close()

    fixed_now = datetime(2026, 6, 8, 4, 0, tzinfo=timezone.utc)
    settings = Settings(
        nightly_idle_restart_enabled=True,
        nightly_idle_restart_cron="0 4 * * *",
        active_web_session_tracking_enabled=True,
        active_web_session_ttl_seconds=180,
    )

    with (
        patch("app.services.nightly_idle_restart_worker.get_settings", return_value=settings),
        patch("app.services.nightly_idle_restart_worker.datetime") as mock_dt,
        patch("app.services.nightly_idle_restart_worker.subprocess.run") as mock_run,
        patch("app.services.nightly_idle_restart_worker.SessionLocal", api_test_env["session_factory"]),
    ):
        mock_dt.now.return_value = fixed_now
        result = run_nightly_idle_restart_once()

    assert result["status"] == "skipped"
    assert result["reason"] == "active_sessions"
    mock_run.assert_not_called()


def test_nightly_restart_runs_when_idle(api_test_env):
    fixed_now = datetime(2026, 6, 8, 4, 0, tzinfo=timezone.utc)
    settings = Settings(
        nightly_idle_restart_enabled=True,
        nightly_idle_restart_cron="0 4 * * *",
        admin_panel_az_service_name="admin-panel-az.service",
        active_web_session_tracking_enabled=True,
    )

    with (
        patch("app.services.nightly_idle_restart_worker.get_settings", return_value=settings),
        patch("app.services.nightly_idle_restart_worker.datetime") as mock_dt,
        patch("app.services.nightly_idle_restart_worker.subprocess.run") as mock_run,
        patch("app.services.nightly_idle_restart_worker.SessionLocal", api_test_env["session_factory"]),
    ):
        mock_dt.now.return_value = fixed_now
        result = run_nightly_idle_restart_once()

    assert result["status"] == "restarted"
    mock_run.assert_called_once()
