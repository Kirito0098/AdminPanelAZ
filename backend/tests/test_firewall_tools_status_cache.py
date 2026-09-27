"""iptables/ipset readiness probe is cached: the IP-restriction middleware reads security settings per request."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services import firewall_tools_check as fw
from app.services.security import SecurityService


def _status(detail: str) -> fw.FirewallToolsStatus:
    return fw.FirewallToolsStatus(
        missing_commands=(),
        missing_packages=(),
        commands_ok=True,
        operational_ok=True,
        operational_detail=detail,
    )


@pytest.fixture
def probes(monkeypatch):
    fw.clear_firewall_tools_status_cache()
    calls: list[int] = []

    def fake_check(*, run_cmd=None):
        calls.append(1)
        return _status(f"probe #{len(calls)}")

    monkeypatch.setattr(fw, "check_firewall_tools", fake_check)
    yield calls
    fw.clear_firewall_tools_status_cache()


def test_status_probed_once_within_ttl(probes):
    first = fw.cached_firewall_tools_status()
    second = fw.cached_firewall_tools_status()

    assert len(probes) == 1
    assert first == second == _status("probe #1")


def test_status_reprobed_after_ttl(probes, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(fw.time, "monotonic", lambda: now[0])

    fw.cached_firewall_tools_status()
    now[0] += fw.FIREWALL_TOOLS_STATUS_TTL_SECONDS - 1
    fw.cached_firewall_tools_status()
    assert len(probes) == 1

    now[0] += 2
    assert fw.cached_firewall_tools_status() == _status("probe #2")
    assert len(probes) == 2


def test_clear_drops_cached_status(probes):
    fw.cached_firewall_tools_status()
    fw.clear_firewall_tools_status_cache()
    fw.cached_firewall_tools_status()

    assert len(probes) == 2


def test_security_settings_reuse_cached_probe(probes, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(SecurityService, "is_whitelist_port_firewall_applicable", lambda self: False)
    try:
        service = SecurityService()
        first = service.get_settings(db)
        second = service.get_settings(db)
    finally:
        db.close()
        engine.dispose()

    assert len(probes) == 1
    assert first["firewall_tools_ready"] is True
    assert first["firewall_tools_detail"] == second["firewall_tools_detail"] == "probe #1"
