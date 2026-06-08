"""Tests for active web session tracking."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.models import ActiveWebSession
from app.services.active_web_session import active_web_session_service


def test_touch_creates_session_row(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        request = MagicMock()
        request.headers = {"User-Agent": "pytest", "X-Forwarded-For": "10.0.0.5"}
        session_id = active_web_session_service.generate_session_id()

        with patch("app.services.active_web_session.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                active_web_session_tracking_enabled=True,
                active_web_session_ttl_seconds=180,
                active_web_session_touch_interval_seconds=30,
            )
            with patch(
                "app.services.ip_restriction.ip_restriction_service.get_client_ip",
                return_value="10.0.0.5",
            ):
                active_web_session_service.touch_active_web_session(
                    db,
                    "api_admin",
                    request=request,
                    session_id=session_id,
                    force=True,
                )

        row = db.query(ActiveWebSession).filter(ActiveWebSession.session_id == session_id).first()
        assert row is not None
        assert row.username == "api_admin"
        assert row.remote_addr == "10.0.0.5"
    finally:
        db.close()


def test_touch_throttled_without_force(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        request = MagicMock()
        request.headers = {"User-Agent": "pytest"}
        session_id = active_web_session_service.generate_session_id()
        settings = Settings(
            active_web_session_tracking_enabled=True,
            active_web_session_ttl_seconds=180,
            active_web_session_touch_interval_seconds=300,
        )

        with patch("app.services.active_web_session.get_settings", return_value=settings):
            with patch(
                "app.services.ip_restriction.ip_restriction_service.get_client_ip",
                return_value="127.0.0.1",
            ):
                active_web_session_service.touch_active_web_session(
                    db, "api_admin", request=request, session_id=session_id, force=True
                )
                first_seen = db.query(ActiveWebSession).filter_by(session_id=session_id).one().last_seen_at
                active_web_session_service.touch_active_web_session(
                    db, "api_admin", request=request, session_id=session_id, force=False
                )
                second_seen = db.query(ActiveWebSession).filter_by(session_id=session_id).one().last_seen_at

        assert first_seen == second_seen
    finally:
        db.close()


def test_tracking_disabled_is_noop(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        request = MagicMock()
        request.headers = {}
        session_id = active_web_session_service.generate_session_id()

        with patch("app.services.active_web_session.get_settings") as mock_settings:
            mock_settings.return_value = Settings(active_web_session_tracking_enabled=False)
            active_web_session_service.touch_active_web_session(
                db, "api_admin", request=request, session_id=session_id, force=True
            )

        assert db.query(ActiveWebSession).count() == 0
    finally:
        db.close()


def test_remove_active_web_session(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        row = ActiveWebSession(
            session_id="abc123",
            username="api_admin",
            created_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()

        active_web_session_service.remove_active_web_session(db, "abc123")
        assert db.query(ActiveWebSession).count() == 0
    finally:
        db.close()


def test_count_active_sessions(api_test_env):
    db = api_test_env["session_factory"]()
    try:
        now = datetime.utcnow()
        db.add(
            ActiveWebSession(
                session_id="fresh",
                username="api_admin",
                created_at=now,
                last_seen_at=now,
            )
        )
        db.add(
            ActiveWebSession(
                session_id="stale",
                username="api_admin",
                created_at=now - timedelta(hours=2),
                last_seen_at=now - timedelta(hours=2),
            )
        )
        db.commit()

        with patch("app.services.active_web_session.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                active_web_session_tracking_enabled=True,
                active_web_session_ttl_seconds=180,
            )
            assert active_web_session_service.count_active_sessions(db) == 1
    finally:
        db.close()
