import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Node, OpenVpnBufferGuardEvent, OpenVpnBufferGuardMode
from app.services import background_gate
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

    monkeypatch.setattr(background_gate.time, "sleep", fake_sleep)

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

    monkeypatch.setattr(background_gate.time, "sleep", fake_sleep)

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


def test_journal_failure_creates_failed_event(db_session, monkeypatch):
    node = _make_node(db_session, is_local=True)

    guard.upsert_settings(
        db_session,
        node.id,
        {
            "enabled": True,
            "mode": OpenVpnBufferGuardMode.kill_restart.value,
            "threshold_count": 10,
            "window_seconds": 60,
            "watch_units": ["antizapret-udp"],
        },
    )

    class FailingAdapter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []
            self.kills: list[tuple[str, str]] = []
            self.restarts: list[str] = []

        def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
            self.calls.append((unit, window_seconds))
            return {"ok": False, "unit": unit, "text": "", "error": "boom"}

        def restart_service(self, service_name: str) -> str:
            self.restarts.append(service_name)
            return "ok"

        def disconnect_openvpn_client(self, client_name: str) -> dict:
            self.kills.append(("*", client_name))
            return {"success": True, "client_name": client_name}

    adapter = FailingAdapter()

    sent_notify: list[dict] = []

    def fake_notify(db, event_type: str, **kwargs) -> None:  # type: ignore[override]
        sent_notify.append({"event_type": event_type, **kwargs})

    monkeypatch.setattr(guard.admin_notify_service, "send", fake_notify)

    results = guard.run_guard_pass(db_session, adapter, node.id, manual=False)

    assert results and results[0]["unit"] == "antizapret-udp"
    assert results[0]["total"] == 0
    assert results[0]["threshold_exceeded"] is False
    assert results[0]["actions"] == []
    assert results[0]["result"] == "failed"

    # Should have notified admins about the failure.
    assert any(n["event_type"] == "openvpn_buffer_guard" for n in sent_notify)

    events = guard.list_events(db_session, node.id, limit=5)
    assert len(events) == 1
    ev = events[0]
    assert ev.result == "failed"
    assert ev.error_count == 0
    detail = json.loads(ev.detail or "{}")
    assert detail.get("sample_ok") is False
    assert "error" in detail


def test_escalation_uses_short_second_window(db_session, monkeypatch):
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

    class RecordingAdapter(FakeAdapter):
        def __init__(self, texts: dict[str, str]):
            super().__init__(texts)
            self.windows: list[int] = []

        def sample_openvpn_journal(self, unit: str, window_seconds: int) -> dict:
            self.windows.append(window_seconds)
            return super().sample_openvpn_journal(unit, window_seconds)

    adapter = RecordingAdapter({"antizapret-udp": _enobufs_text("client-y", count=6)})

    monkeypatch.setattr(
        guard.openvpn_management_service,
        "kill_client",
        lambda profile_key, client_name: {"success": True, "profile": profile_key, "client_name": client_name},
    )

    monkeypatch.setattr(background_gate.time, "sleep", lambda seconds: None)

    results = guard.run_guard_pass(db_session, adapter, node.id, manual=False)

    assert results
    # First sample uses the full window; second sample should use a short window
    # close to escalate_after_seconds to avoid counting pre-kill ENOBUFS.
    assert adapter.windows[0] == settings.window_seconds
    assert adapter.windows[1] == max(5, settings.escalate_after_seconds)


def test_temp_ban_expiry_uses_per_node_adapter(db_session, monkeypatch):
    node_local = _make_node(db_session, is_local=True)
    node_remote = _make_node(db_session, is_local=False)

    now = datetime.now(timezone.utc)

    ev_local = OpenVpnBufferGuardEvent(
        node_id=node_local.id,
        created_at=now - timedelta(minutes=1),
        unit="vpn-udp",
        common_name="local-client",
        real_address=None,
        error_count=0,
        window_seconds=60,
        mode=OpenVpnBufferGuardMode.kill_restart_temp_ban.value,
        actions_json="[]",
        result="banned",
        detail=None,
        manual=False,
        ban_expires_at=now - timedelta(seconds=1),
    )
    ev_remote = OpenVpnBufferGuardEvent(
        node_id=node_remote.id,
        created_at=now - timedelta(minutes=1),
        unit="vpn-udp",
        common_name="remote-client",
        real_address=None,
        error_count=0,
        window_seconds=60,
        mode=OpenVpnBufferGuardMode.kill_restart_temp_ban.value,
        actions_json="[]",
        result="banned",
        detail=None,
        manual=False,
        ban_expires_at=now - timedelta(seconds=1),
    )
    db_session.add_all([ev_local, ev_remote])
    db_session.commit()

    class DummyAdapter:
        def __init__(self, label: str) -> None:
            self.label = label

    adapters_by_node: dict[int, DummyAdapter] = {}

    def fake_get_adapter_for_node(node: Node) -> DummyAdapter:
        adapter = DummyAdapter(f"adapter-{node.id}")
        adapters_by_node[node.id] = adapter
        return adapter

    import app.services.node_manager as node_manager_mod

    monkeypatch.setattr(node_manager_mod, "get_adapter_for_node", fake_get_adapter_for_node)

    access_policy_calls: list[tuple[int, str]] = []

    class FakeAccessPolicyService:
        def __init__(self, db, *, antizapret_path, node_id, node_name, adapter) -> None:  # type: ignore[override]
            _ = (db, antizapret_path, node_name)
            assert isinstance(adapter, DummyAdapter)
            access_policy_calls.append((node_id, adapter.label))
            self.node_id = node_id
            self.banned = {"local-client", "remote-client"}

        def read_banned_clients(self) -> set[str]:
            return set(self.banned)

        def reconcile_openvpn(self, client_name: str) -> None:
            # Simulate write failure for remote node to ensure we don't clear bans.
            if self.node_id == node_remote.id:
                raise RuntimeError("write failed")
            self.banned.discard(client_name)

    import app.services.access_policy as access_policy_mod

    monkeypatch.setattr(access_policy_mod, "AccessPolicyService", FakeAccessPolicyService)

    results = guard.process_temp_ban_expiries(db_session)

    # Local node ban should be cleared; remote node should stay banned due to write failure.
    assert {"node_id": node_local.id, "client_name": "local-client", "unbanned": True} in results
    assert all(r["node_id"] != node_remote.id for r in results)

    db_session.refresh(ev_local)
    db_session.refresh(ev_remote)
    assert ev_local.ban_expires_at is None
    assert ev_remote.ban_expires_at is not None

    # Adapters must be resolved per node.
    assert access_policy_calls
    assert (node_local.id, f"adapter-{node_local.id}") in access_policy_calls
    assert (node_remote.id, f"adapter-{node_remote.id}") in access_policy_calls


def test_recommended_thresholds_by_mode():
    assert guard.recommended_threshold("notify") == 40
    assert guard.recommended_threshold("kill") == 80
    assert guard.recommended_threshold("kill_restart") == 120
    assert guard.recommended_threshold("kill_restart_temp_ban") == 150
    assert guard.recommended_threshold("nope") == 40
    assert guard.recommended_by_mode() == {
        "notify": 40,
        "kill": 80,
        "kill_restart": 120,
        "kill_restart_temp_ban": 150,
    }


def test_get_settings_defaults_are_notify_and_40(db_session):
    node = _make_node(db_session)
    row = guard.get_settings(db_session, node.id)
    assert row.mode == OpenVpnBufferGuardMode.notify.value
    assert row.threshold_count == 40
    assert row.window_seconds == 60
    assert row.enabled is False

