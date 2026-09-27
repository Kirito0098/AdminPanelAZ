"""Buffer Guard: неизвестный режим, чистка событий, пауза восстановления бэкапа, старый агент."""

from __future__ import annotations

import asyncio
import fcntl
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, OpenVpnBufferGuardEvent, OpenVpnBufferGuardMode, OpenVpnBufferGuardSettings
from app.routers import openvpn_buffer_guard as api
from app.services import background_gate, retention
from app.services import openvpn_buffer_guard as guard
from app.services import openvpn_buffer_guard_worker as guard_worker


class GuardAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.killed = threading.Event()

    def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
        self.calls.append("sample")
        text = "\n".join(["noisy/udp4:203.0.113.1:1194 note: No buffer space available"] * 10)
        return {"ok": True, "unit": unit, "text": text, "error": None}

    def kill_openvpn_client(self, unit: str, client_name: str) -> dict:
        self.calls.append("kill")
        self.killed.set()
        return {"success": True}

    def restart_service(self, service_name: str) -> str:
        self.calls.append("restart")
        return "ok"


class OldAgentAdapter(GuardAdapter):
    def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
        raise HTTPException(status_code=404, detail={"code": "error", "message": "Not Found"})


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def quiet_notify(monkeypatch):
    monkeypatch.setattr(guard.admin_notify_service, "send", lambda *a, **k: None)


@pytest.fixture()
def gate(tmp_path):
    db_path = tmp_path / "adminpanel.db"
    background_gate.configure_background_gate(db_path)
    yield db_path
    background_gate.resume_background_work()
    background_gate.configure_background_gate(None)


def _node(db, mode: str, **settings) -> Node:
    row = Node(name="node-a", host="10.0.0.2", is_local=False, status=NodeStatus.online)
    db.add(row)
    db.commit()
    db.refresh(row)
    guard.upsert_settings(
        db,
        row.id,
        {"enabled": True, "threshold_count": 5, "watch_units": ["antizapret-udp"], **settings},
    )
    db.query(OpenVpnBufferGuardSettings).filter_by(node_id=row.id).update({"mode": mode})
    db.commit()
    return row


def test_unknown_mode_only_notifies(db):
    node = _node(db, "kill_everything")
    adapter = GuardAdapter()

    results = guard.run_guard_pass(db, adapter, node.id)

    assert adapter.calls == ["sample"]
    assert results[0]["mode"] == OpenVpnBufferGuardMode.notify.value
    assert results[0]["result"] == "notified"


def _event(node_id: int, created_at: datetime, *, ban_expires_at: datetime | None = None) -> OpenVpnBufferGuardEvent:
    return OpenVpnBufferGuardEvent(
        node_id=node_id,
        created_at=created_at,
        unit="antizapret-udp",
        common_name="noisy",
        error_count=10,
        window_seconds=60,
        mode="notify",
        result="notified",
        ban_expires_at=ban_expires_at,
    )


def test_retention_purges_old_buffer_guard_events(db, monkeypatch):
    node = _node(db, "notify")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add_all(
        [
            _event(node.id, now - timedelta(days=31)),
            _event(node.id, now - timedelta(days=29)),
            _event(node.id, now - timedelta(days=40), ban_expires_at=now - timedelta(days=39)),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        retention,
        "get_settings",
        lambda: SimpleNamespace(
            retention_batch_size=100,
            traffic_sample_retention_days=90,
            action_log_retention_days=365,
            resource_metrics_retention_days=30,
            panel_resource_metrics_retention_days=30,
            traffic_session_retention_days=30,
        ),
    )

    counts = retention.run_retention_purge(db)

    assert counts["openvpn_buffer_guard_events"] == 1
    left = sorted((now - ev.created_at).days for ev in db.query(OpenVpnBufferGuardEvent).all())
    assert left == [29, 40]


def test_sleep_unless_paused_stops_when_restore_waits(gate):
    assert background_gate.sleep_unless_paused(0.2) is True

    intent_fd = background_gate._try_flock(background_gate._lock_paths(gate)[0], fcntl.LOCK_EX)
    try:
        started = time.monotonic()
        assert background_gate.sleep_unless_paused(30) is False
        assert time.monotonic() - started < 2
    finally:
        background_gate._unlock(intent_fd)


def test_escalation_wait_releases_restore_pause(db, gate):
    node = _node(db, OpenVpnBufferGuardMode.kill_restart.value, escalate_after_seconds=8)
    adapter = GuardAdapter()
    outcome: dict = {}

    def run_step():
        outcome["results"] = asyncio.run(background_gate.run_background_step(guard.run_guard_pass, db, adapter, node.id))

    worker = threading.Thread(target=run_step)
    worker.start()
    try:
        assert adapter.killed.wait(5)
        started = time.monotonic()
        background_gate.pause_background_work(gate, timeout=4)
        assert time.monotonic() - started < 3
    finally:
        background_gate.resume_background_work()
        worker.join(15)

    assert adapter.calls == ["sample", "kill"]
    assert outcome["results"][0]["result"] == "killed"
    actions = outcome["results"][0]["actions"]
    assert [a["type"] for a in actions] == ["kill", "escalation_check"]
    assert "восстановление" in actions[1]["result"]


def test_worker_stops_between_nodes_when_restore_waits(session_factory, gate, monkeypatch):
    db = session_factory()
    _node(db, "notify")
    db.close()
    calls: list[int] = []
    monkeypatch.setattr(guard_worker, "SessionLocal", session_factory)
    monkeypatch.setattr(guard_worker, "get_adapter_for_node", lambda node: GuardAdapter())
    monkeypatch.setattr(guard_worker, "run_guard_pass", lambda db, adapter, node_id, manual=False: calls.append(node_id))
    monkeypatch.setattr(guard_worker, "process_temp_ban_expiries", lambda db: [])

    intent_fd = background_gate._try_flock(background_gate._lock_paths(gate)[0], fcntl.LOCK_EX)
    try:
        guard_worker._run_once()
    finally:
        background_gate._unlock(intent_fd)
    assert calls == []

    guard_worker._run_once()
    assert len(calls) == 1


def test_old_agent_raises_clear_error(db):
    node = _node(db, "notify")

    with pytest.raises(guard.BufferGuardAgentOutdated, match="обновите агент"):
        guard.run_guard_pass(db, OldAgentAdapter(), node.id)


def test_other_agent_errors_are_not_reported_as_outdated(db):
    node = _node(db, "notify")

    class BrokenAgent(GuardAdapter):
        def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
            raise HTTPException(status_code=502, detail="agent unreachable")

    with pytest.raises(HTTPException) as exc_info:
        guard.run_guard_pass(db, BrokenAgent(), node.id)
    assert exc_info.value.status_code == 502


def test_manual_scan_on_old_agent_answers_409(db, monkeypatch):
    node = _node(db, "notify")
    monkeypatch.setattr(api, "get_adapter_for_node", lambda node: OldAgentAdapter())

    with pytest.raises(HTTPException) as exc_info:
        api.scan_openvpn_buffer_guard(api.OpenVpnBufferGuardScanRequest(node_id=node.id), db=db, _=None)

    assert exc_info.value.status_code == 409
    assert "обновите агент" in exc_info.value.detail


def test_worker_warns_once_about_old_agent(session_factory, monkeypatch, caplog):
    db = session_factory()
    node_id = _node(db, "notify").id
    db.close()
    monkeypatch.setattr(guard_worker, "SessionLocal", session_factory)
    monkeypatch.setattr(guard_worker, "get_adapter_for_node", lambda node: OldAgentAdapter())
    monkeypatch.setattr(guard_worker, "_outdated_agent_nodes", set())

    with caplog.at_level(logging.INFO, logger=guard_worker.logger.name):
        guard_worker._run_once()
        guard_worker._run_once()

    records = [r for r in caplog.records if r.name == guard_worker.logger.name]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is None
    assert "обновите агент" in records[0].getMessage()

    monkeypatch.setattr(guard_worker, "get_adapter_for_node", lambda node: GuardAdapter())
    assert guard_worker._outdated_agent_nodes == {node_id}
    guard_worker._run_once()
    assert guard_worker._outdated_agent_nodes == set()
