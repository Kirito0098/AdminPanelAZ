"""Security scanner dwell/window settings (phase 31 parity with AdminAntizapret)."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSetting
from app.services.ip_restriction import IpRestrictionService
from app.services.scanner_firewall_store import ScannerFirewallStore
from app.services.security import SecurityService
from tests.conftest import run_async


@pytest.fixture()
def security_db(tmp_path):
    db_path = tmp_path / "scanner_settings.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add_all(
        [
            AppSetting(key="security_ip_restriction", value="true"),
            AppSetting(key="security_allowed_ips", value="10.0.0.1"),
            AppSetting(key="security_block_scanners", value="true"),
            AppSetting(key="security_scanner_max_attempts", value="3"),
            AppSetting(key="security_scanner_ban_seconds", value="120"),
        ]
    )
    session.commit()
    yield session, Session
    session.close()


def test_security_service_persists_scanner_dwell_settings(security_db):
    session, _ = security_db
    service = SecurityService()

    result = service.update_settings(
        session,
        {
            "scanner_window_seconds": 90,
            "block_ip_blocked_dwell": False,
            "ip_blocked_dwell_seconds": 180,
        },
    )

    assert result["scanner_window_seconds"] == 90
    assert result["block_ip_blocked_dwell"] is False
    assert result["ip_blocked_dwell_seconds"] == 180


def test_security_service_clamps_scanner_ranges(security_db):
    session, _ = security_db
    service = SecurityService()

    result = service.update_settings(
        session,
        {
            "scanner_window_seconds": 5,
            "ip_blocked_dwell_seconds": 10,
        },
    )

    assert result["scanner_window_seconds"] == 10
    assert result["ip_blocked_dwell_seconds"] == 30


def test_ip_restriction_uses_scanner_window_from_db(security_db, tmp_path):
    session, _ = security_db
    session.add(AppSetting(key="security_scanner_window_seconds", value="120"))
    session.commit()

    store = ScannerFirewallStore(tmp_path / "scanner_blocks.json", dry_run=True)
    service = IpRestrictionService()

    with patch.object(service, "_firewall", store):
        runtime = service._scanner_runtime_settings(session)
        assert runtime["scanner_window_seconds"] == 120


def test_touch_ip_blocked_respects_disabled_dwell(security_db):
    session, _ = security_db
    session.add(AppSetting(key="security_block_ip_blocked_dwell", value="false"))
    session.commit()

    service = IpRestrictionService()
    result = service.touch_ip_blocked_presence(session, "203.0.113.9")
    assert result["tracking"] is False


def test_security_api_returns_scanner_dwell_fields(api_test_env):
    transport = ASGITransport(app=api_test_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/security", headers=api_test_env["admin_headers"])

    response = run_async(_call())
    assert response.status_code == 200
    payload = response.json()
    assert payload["scanner_window_seconds"] == 60
    assert payload["block_ip_blocked_dwell"] is True
    assert payload["ip_blocked_dwell_seconds"] == 120
