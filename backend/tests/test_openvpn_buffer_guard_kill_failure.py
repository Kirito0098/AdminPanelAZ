"""Buffer Guard: неудачный kill пишет событие, не считается успехом и не мешает эскалации."""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, OpenVpnBufferGuardMode
from app.services import openvpn_buffer_guard as guard


class GuardAdapter:
    def __init__(self, calls: list[str], *, kill=None, second_sample=None, restart=None) -> None:
        self.calls = calls
        self.kill = kill or (lambda: {"success": True})
        self.second_sample = second_sample
        self.restart = restart or (lambda: "ok")
        self.samples = 0

    def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
        self.samples += 1
        if self.samples > 1 and self.second_sample is not None:
            return self.second_sample()
        text = "\n".join(["noisy/udp4:203.0.113.1:1194 note: No buffer space available"] * 10)
        return {"ok": True, "unit": unit, "text": text, "error": None}

    def kill_openvpn_client(self, unit: str, client_name: str) -> dict:
        self.calls.append("kill")
        return self.kill()

    def restart_service(self, service_name: str) -> str:
        self.calls.append("restart")
        return self.restart()


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
def calls(monkeypatch) -> list[str]:
    log: list[str] = []
    monkeypatch.setattr(guard.time, "sleep", lambda seconds: None)
    return log


@pytest.fixture()
def notices(monkeypatch, calls) -> list[dict]:
    sent: list[dict] = []

    def fake_send(db, event_type, **kwargs):
        calls.append("notify")
        sent.append(kwargs)

    monkeypatch.setattr(guard.admin_notify_service, "send", fake_send)
    return sent


def _node(db, mode: OpenVpnBufferGuardMode) -> Node:
    row = Node(name="node-a", host="10.0.0.2", is_local=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    guard.upsert_settings(
        db,
        row.id,
        {
            "enabled": True,
            "mode": mode.value,
            "threshold_count": 5,
            "escalate_after_seconds": 10,
            "cooldown_minutes": 15,
            "watch_units": ["antizapret-udp"],
        },
    )
    return row


def _agent_error():
    raise HTTPException(status_code=502, detail={"code": "error", "message": "agent unreachable"})


def test_kill_exception_writes_failed_event_and_starts_cooldown(db, calls, notices):
    node = _node(db, OpenVpnBufferGuardMode.kill)
    adapter = GuardAdapter(calls, kill=_agent_error)

    results = guard.run_guard_pass(db, adapter, node.id)

    assert results[0]["result"] == "failed"
    events = guard.list_events(db, node.id)
    assert [ev.result for ev in events] == ["failed"]
    kill_action = json.loads(events[0].actions_json)[0]
    assert kill_action["type"] == "kill" and kill_action["success"] is False
    assert kill_action["result"]["message"] == "agent unreachable"
    assert len(notices) == 1 and "agent unreachable" in notices[0]["details"]

    assert guard.run_guard_pass(db, adapter, node.id) == []
    assert len(notices) == 1


def test_unsuccessful_kill_is_not_reported_as_killed(db, calls, notices):
    node = _node(db, OpenVpnBufferGuardMode.kill)
    adapter = GuardAdapter(calls, kill=lambda: {"success": False, "message": "Сокет antizapret-udp недоступен"})

    results = guard.run_guard_pass(db, adapter, node.id)

    assert results[0]["result"] == "failed"
    assert guard.list_events(db, node.id)[0].result == "failed"
    assert "Сокет antizapret-udp недоступен" in notices[0]["details"]


def test_notification_is_sent_after_actions_with_outcome(db, calls, notices):
    node = _node(db, OpenVpnBufferGuardMode.kill)
    adapter = GuardAdapter(calls)

    results = guard.run_guard_pass(db, adapter, node.id)

    assert results[0]["result"] == "killed"
    assert calls == ["kill", "notify"]
    assert "клиент отключён" in notices[0]["details"]


def test_kill_failure_still_escalates_to_restart(db, calls, notices):
    node = _node(db, OpenVpnBufferGuardMode.kill_restart)
    adapter = GuardAdapter(calls, kill=_agent_error)

    results = guard.run_guard_pass(db, adapter, node.id)

    assert calls == ["kill", "restart", "notify"]
    assert results[0]["result"] == "restarted"


def test_failed_escalation_check_keeps_event(db, calls, notices):
    node = _node(db, OpenVpnBufferGuardMode.kill_restart)
    adapter = GuardAdapter(calls, second_sample=_agent_error)

    results = guard.run_guard_pass(db, adapter, node.id)

    assert calls == ["kill", "notify"]
    assert results[0]["result"] == "killed"
    assert [ev.result for ev in guard.list_events(db, node.id)] == ["killed"]
    assert "agent unreachable" in notices[0]["details"]


def test_failed_restart_is_not_reported_as_restarted(db, calls, notices):
    node = _node(db, OpenVpnBufferGuardMode.kill_restart)
    adapter = GuardAdapter(calls, kill=lambda: {"success": False, "message": "no socket"}, restart=_agent_error)

    results = guard.run_guard_pass(db, adapter, node.id)

    assert calls == ["kill", "restart", "notify"]
    assert results[0]["result"] == "failed"
