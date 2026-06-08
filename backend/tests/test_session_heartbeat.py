"""Tests for GET /api/session-heartbeat."""

from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.models import ActiveWebSession
from app.services.active_web_session import WEB_SESSION_ID_HEADER


def test_session_heartbeat_requires_auth(api_test_env):
    client = TestClient(api_test_env["app"])
    response = client.get("/api/session-heartbeat")
    assert response.status_code == 401


def test_session_heartbeat_updates_last_seen(api_test_env):
    client = TestClient(api_test_env["app"])
    db = api_test_env["session_factory"]()
    session_id = "deadbeef" * 2
    try:
        row = ActiveWebSession(
            session_id=session_id,
            username="api_admin",
            created_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow() - timedelta(minutes=10),
        )
        db.add(row)
        db.commit()
        old_seen = row.last_seen_at

        with patch("app.services.active_web_session.get_settings") as mock_settings:
            mock_settings.return_value = Settings(
                active_web_session_tracking_enabled=True,
                active_web_session_ttl_seconds=180,
                active_web_session_touch_interval_seconds=30,
            )
            headers = {
                **api_test_env["admin_headers"],
                WEB_SESSION_ID_HEADER: session_id,
            }
            response = client.get("/api/session-heartbeat", headers=headers)

        assert response.status_code == 200
        assert response.json()["success"] is True
        db.refresh(row)
        assert row.last_seen_at >= old_seen
    finally:
        db.close()


def test_session_heartbeat_succeeds_when_tracking_disabled(api_test_env):
    client = TestClient(api_test_env["app"])
    with patch("app.services.active_web_session.get_settings") as mock_settings:
        mock_settings.return_value = Settings(active_web_session_tracking_enabled=False)
        response = client.get("/api/session-heartbeat", headers=api_test_env["admin_headers"])
    assert response.status_code == 200
    assert response.json()["success"] is True
