"""IP restriction and scanner ban tests (ported from AdminAntizapret)."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import AppSetting
from app.services.ip_restriction import IpRestrictionService
from app.services.scanner_firewall_store import ScannerFirewallStore
from tests.conftest import run_async


def _security_settings(*, enabled: bool = True, block_scanners: bool = True, allowed: str = "10.0.0.1"):
    return [
        AppSetting(key="security_ip_restriction", value="true" if enabled else "false"),
        AppSetting(key="security_allowed_ips", value=allowed),
        AppSetting(key="security_block_scanners", value="true" if block_scanners else "false"),
        AppSetting(key="security_scanner_max_attempts", value="3"),
        AppSetting(key="security_scanner_ban_seconds", value="120"),
    ]


@pytest.fixture()
def ip_restriction_env(tmp_path):
    db_path = tmp_path / "ip_restriction.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add_all(_security_settings())
    session.commit()

    store = ScannerFirewallStore(tmp_path / "scanner_blocks.json", dry_run=True)
    service = IpRestrictionService()
    yield session, Session, service, store, tmp_path
    session.close()


def test_rate_limit_then_hard_deny(ip_restriction_env):
    session, _Session, service, store, _tmp = ip_restriction_env
    with patch.object(service, "_firewall", store):
        ip = "203.0.113.5"
        assert service.should_hard_deny(session, ip) is False
        service.record_denied_access(session, ip)
        service.record_denied_access(session, ip)
        service.record_denied_access(session, ip)
        assert service.should_hard_deny(session, ip) is True


def test_ip_blocked_unavailable_when_restrictions_disabled(ip_restriction_env):
    session, SessionFactory, _service, _store, _tmp = ip_restriction_env
    session.query(AppSetting).filter(AppSetting.key == "security_ip_restriction").update({"value": "false"})
    session.commit()

    from app.main import app

    def override_get_db():
        db = SessionFactory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        with patch("app.database.SessionLocal", SessionFactory):
            async def _call():
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    page = await client.get("/ip-blocked", follow_redirects=False)
                    ping = await client.get("/api/ip-blocked/ping")
                    return page, ping

            page, ping = run_async(_call())
        assert page.status_code == 302
        assert "/login" in page.text
        assert ping.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_denied_ip_api_returns_403(ip_restriction_env):
    session, SessionFactory, service, store, _tmp = ip_restriction_env

    from app.main import app

    def override_get_db():
        db = SessionFactory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with (
        patch.object(service, "_firewall", store),
        patch("app.main.ip_restriction_service.get_client_ip", return_value="203.0.113.9"),
        patch("app.main.ip_restriction_service", service),
        patch("app.database.SessionLocal", SessionFactory),
    ):
        transport = ASGITransport(app=app)

        async def _call():
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get(
                    "/api/users",
                    headers={"Accept": "application/json"},
                )

        response = run_async(_call())
    app.dependency_overrides.clear()
    assert response.status_code == 403
    assert "IP" in response.json().get("detail", "")
