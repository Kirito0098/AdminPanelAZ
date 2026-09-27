"""Cooldown Buffer Guard: что отключает автозащиту узла после события, а что нет."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, OpenVpnBufferGuardMode
from app.services import openvpn_buffer_guard as guard


class JournalAdapter:
    def __init__(self) -> None:
        self.text = ""
        self.error: str | None = None
        self.kills: list[tuple[str, str]] = []

    def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
        if self.error:
            return {"ok": False, "unit": unit, "text": "", "error": self.error}
        return {"ok": True, "unit": unit, "text": self.text, "error": None}

    def kill_openvpn_client(self, unit: str, client_name: str) -> dict:
        self.kills.append((unit, client_name))
        return {"success": True, "client_name": client_name}


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def notices(monkeypatch) -> list[dict]:
    sent: list[dict] = []
    monkeypatch.setattr(guard.admin_notify_service, "send", lambda db, event_type, **kw: sent.append(kw))
    return sent


@pytest.fixture()
def node(db) -> Node:
    row = Node(name="node-a", host="10.0.0.2", is_local=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    guard.upsert_settings(
        db,
        row.id,
        {
            "enabled": True,
            "mode": OpenVpnBufferGuardMode.kill.value,
            "threshold_count": 5,
            "cooldown_minutes": 15,
            "watch_units": ["antizapret-udp"],
        },
    )
    return row


def _enobufs(common_name: str, count: int) -> str:
    return "\n".join([f"{common_name}/udp4:203.0.113.1:1194 note: No buffer space available"] * count)


def test_manual_scan_does_not_start_cooldown(db, node, notices):
    adapter = JournalAdapter()
    adapter.text = _enobufs("noisy", 10)

    manual = guard.run_guard_pass(db, adapter, node.id, manual=True)
    assert manual[0]["result"] == "notified"
    assert adapter.kills == []

    auto = guard.run_guard_pass(db, adapter, node.id)

    assert auto and auto[0]["result"] == "killed"
    assert adapter.kills == [("antizapret-udp", "noisy")]


def test_journal_failure_does_not_start_cooldown(db, node, notices):
    adapter = JournalAdapter()
    adapter.error = "journalctl: timeout"
    failed = guard.run_guard_pass(db, adapter, node.id)
    assert failed[0]["result"] == "failed"

    adapter.error = None
    adapter.text = _enobufs("noisy", 10)
    auto = guard.run_guard_pass(db, adapter, node.id)

    assert auto and auto[0]["result"] == "killed"
    assert adapter.kills == [("antizapret-udp", "noisy")]


def test_repeated_journal_failure_is_reported_once_per_cooldown(db, node, notices):
    adapter = JournalAdapter()
    adapter.error = "journalctl: timeout"

    for _ in range(3):
        results = guard.run_guard_pass(db, adapter, node.id)
        assert results[0]["result"] == "failed"

    assert len(notices) == 1
    events = guard.list_events(db, node.id)
    assert [ev.result for ev in events] == ["failed"]


def test_journal_failure_throttle_is_per_unit(db, node, notices):
    guard.upsert_settings(db, node.id, {"watch_units": ["antizapret-udp", "vpn-udp"]})

    class PerUnitAdapter(JournalAdapter):
        failing: set[str] = set()

        def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
            if unit in self.failing:
                return {"ok": False, "unit": unit, "text": "", "error": "boom"}
            return {"ok": True, "unit": unit, "text": "", "error": None}

    adapter = PerUnitAdapter()
    adapter.failing = {"antizapret-udp"}
    guard.run_guard_pass(db, adapter, node.id)
    adapter.failing = {"vpn-udp"}
    guard.run_guard_pass(db, adapter, node.id)

    assert [n["details"].split(":")[0] for n in notices] == [
        "journal sample failed for antizapret-udp",
        "journal sample failed for vpn-udp",
    ]


def test_journal_failure_is_reported_each_pass_without_cooldown(db, node, notices):
    guard.upsert_settings(db, node.id, {"cooldown_minutes": 0})
    adapter = JournalAdapter()
    adapter.error = "journalctl: timeout"

    guard.run_guard_pass(db, adapter, node.id)
    guard.run_guard_pass(db, adapter, node.id)

    assert len(notices) == 2


def test_manual_journal_failure_is_always_reported(db, node, notices):
    adapter = JournalAdapter()
    adapter.error = "journalctl: timeout"

    guard.run_guard_pass(db, adapter, node.id)
    manual = guard.run_guard_pass(db, adapter, node.id, manual=True)

    assert manual[0]["result"] == "failed"
    assert len(notices) == 2
    assert [ev.manual for ev in guard.list_events(db, node.id)] == [True, False]


def test_automatic_action_still_starts_cooldown(db, node, notices):
    adapter = JournalAdapter()
    adapter.text = _enobufs("noisy", 10)

    first = guard.run_guard_pass(db, adapter, node.id)
    second = guard.run_guard_pass(db, adapter, node.id)

    assert first[0]["result"] == "killed"
    assert second == []
    assert adapter.kills == [("antizapret-udp", "noisy")]


def test_manual_scan_ignores_cooldown(db, node, notices):
    adapter = JournalAdapter()
    adapter.text = _enobufs("noisy", 10)
    guard.run_guard_pass(db, adapter, node.id)

    manual = guard.run_guard_pass(db, adapter, node.id, manual=True)

    assert manual and manual[0]["threshold_exceeded"] is True
    assert manual[0]["actions"] == []
