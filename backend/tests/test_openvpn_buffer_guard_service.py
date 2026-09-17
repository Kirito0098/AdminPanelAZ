import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, OpenVpnBufferGuardEvent, OpenVpnBufferGuardMode
from app.services import openvpn_buffer_guard as guard


class FakeAdapter:
    def __init__(self, texts: dict[str, str]):
        self.texts = texts
        self.kills: list[tuple[str, str]] = []
        self.restarts: list[str] = []

    def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
        return {
            "ok": True,
            "unit": unit,
            "text": self.texts.get(unit, ""),
            "error": None,
        }

    def restart_service(self, service_name: str) -> str:
        self.restarts.append(service_name)
        return "ok"

    # For compatibility with real adapters; not used directly in tests.
    def disconnect_openvpn_client(self, client_name: str) -> dict:
        self.kills.append(("*", client_name))
        return {"success": True, "client_name": client_name}


def _make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    return engine, session


@pytest.fixture()
def db_session():
    engine, session = _make_db()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_node(db, *, is_local: bool = True) -> Node:
    node = Node(
        name="test-node",
        host="127.0.0.1",
        is_local=is_local,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _enobufs_text(common_name: str, count: int = 3) -> str:
    line = f"{common_name}/udp4:203.0.113.1:1194 note: No buffer space available"
    return "\n".join([line] * count)


def test_notify_mode_does_not_kill(db_session, monkeypatch):
    node = _make_node(db_session, is_local=True)

    guard.upsert_settings(
        db_session,
        node.id,
        {
            "enabled": True,
            "mode": OpenVpnBufferGuardMode.notify.value,
            "threshold_count": 2,
            "window_seconds": 60,
            "watch_units": ["antizapret-udp"],
        },
    )

    adapter = FakeAdapter({"antizapret-udp": _enobufs_text("client-x", count=3)})

    kills: list[tuple[str, str]] = []

    def fake_kill_client(profile_key: str, client_name: str) -> dict:
        kills.append((profile_key, client_name))
        return {"success": True}

    monkeypatch.setattr(guard.openvpn_management_service, "kill_client", fake_kill_client)

    # Silence / observe admin notifications.
    sent_notify: list[dict] = []

    def fake_notify(db, event_type: str, **kwargs) -> None:  # type: ignore[override]
        sent_notify.append({"event_type": event_type, **kwargs})

    monkeypatch.setattr(guard.admin_notify_service, "send", fake_notify)

    results = guard.run_guard_pass(db_session, adapter, node.id, manual=False)

    assert results, "run_guard_pass should return at least one unit result"
    assert all(r.get("unit") == "antizapret-udp" for r in results)
    assert kills == [], "notify mode must not kill clients"
    assert adapter.kills == [], "adapter.disconnect_openvpn_client must not be called in notify mode"

    events = guard.list_events(db_session, node.id, limit=5)
    assert len(events) == 1
    ev: OpenVpnBufferGuardEvent = events[0]
    assert ev.mode == OpenVpnBufferGuardMode.notify.value
    assert ev.error_count == 3
    assert ev.common_name == "client-x"
    assert ev.result == "notified"
    assert results[0]["result"] == "notified"


def test_kill_restart_escalates(db_session, monkeypatch):
    node = _make_node(db_session, is_local=True)

    settings = guard.upsert_settings(
        db_session,
        node.id,
        {
            "enabled": True,
            "mode": OpenVpnBufferGuardMode.kill_restart.value,
            "threshold_count": 4,
            "window_seconds": 60,
            "escalate_after_seconds": 10,
            "watch_units": ["antizapret-udp"],
        },
    )

    adapter = FakeAdapter({"antizapret-udp": _enobufs_text("client-y", count=6)})

    kills: list[tuple[str, str]] = []

    def fake_kill_client(profile_key: str, client_name: str) -> dict:
        kills.append((profile_key, client_name))
        return {"success": True}

    monkeypatch.setattr(guard.openvpn_management_service, "kill_client", fake_kill_client)

    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(guard.time, "sleep", fake_sleep)

    results = guard.run_guard_pass(db_session, adapter, node.id, manual=False)

    assert results, "run_guard_pass should inspect at least one unit"
    assert kills == [("antizapret-udp", "client-y")]
    assert adapter.restarts == ["openvpn-server@antizapret-udp"]
    assert slept == [float(settings.escalate_after_seconds)]

    events = guard.list_events(db_session, node.id, limit=10)
    assert events, "event must be persisted on escalation"
    ev = events[0]
    assert ev.mode == OpenVpnBufferGuardMode.kill_restart.value
    assert ev.common_name == "client-y"
    assert ev.error_count == 6
    assert json.loads(ev.actions_json or "[]"), "actions_json should record performed actions"
    assert ev.result == "restarted"
    assert results[0]["result"] == "restarted"


def test_manual_scan_with_disabled_settings_runs_findings_only(db_session, monkeypatch):
    node = _make_node(db_session, is_local=True)

    guard.upsert_settings(
        db_session,
        node.id,
        {
            "enabled": False,
            "mode": OpenVpnBufferGuardMode.kill_restart.value,
            "threshold_count": 2,
            "window_seconds": 60,
            "watch_units": ["antizapret-udp"],
        },
    )

    adapter = FakeAdapter({"antizapret-udp": _enobufs_text("client-z", count=3)})

    kills: list[tuple[str, str]] = []

    def fake_kill_client(profile_key: str, client_name: str) -> dict:
        kills.append((profile_key, client_name))
        return {"success": True}

    monkeypatch.setattr(guard.openvpn_management_service, "kill_client", fake_kill_client)

    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(guard.time, "sleep", fake_sleep)

    results = guard.run_guard_pass(db_session, adapter, node.id, manual=True)

    assert results, "manual run should still return findings"
    assert results[0]["threshold_exceeded"] is True
    assert results[0]["actions"] == []
    assert results[0]["result"] == "notified"
    assert kills == []
    assert adapter.kills == []
    assert adapter.restarts == []
    assert slept == []

    events = guard.list_events(db_session, node.id, limit=5)
    assert len(events) == 1
    ev = events[0]
    assert ev.mode == OpenVpnBufferGuardMode.kill_restart.value
    assert ev.common_name == "client-z"
    assert ev.error_count == 3
    assert ev.result == "notified"

