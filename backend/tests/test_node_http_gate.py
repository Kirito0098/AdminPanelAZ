"""Per-node agent request gate: serialize remote calls, skip when busy, bounded wait."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi import HTTPException

from app.services import node_http_gate as gate
from app.services.node_adapter import RemoteNodeAdapter


@pytest.fixture(autouse=True)
def _reset_gate(tmp_path, monkeypatch):
    gate.configure_node_http_gate(None)
    with gate._locks_guard:
        gate._locks.clear()
    monkeypatch.setattr(gate, "_lock_dir", None, raising=False)
    yield
    gate.configure_node_http_gate(None)
    with gate._locks_guard:
        gate._locks.clear()


class FakeResp:
    status_code = 200
    content = b'{"ok":true}'

    @staticmethod
    def json():
        return {"ok": True}


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def request(self, method, url, **kwargs):
        self.calls.append(url)
        return FakeResp()


def _adapter(monkeypatch) -> tuple[RemoteNodeAdapter, FakeClient]:
    adapter = RemoteNodeAdapter("127.0.0.1", 9100, "key", mtls_enabled=False)
    client = FakeClient()
    monkeypatch.setattr(adapter, "_get_http_client", lambda: client)
    return adapter, client


class _Holder:
    """Hold a node slot in another thread until released."""

    def __init__(self, key: str) -> None:
        self._key = key
        self._held = threading.Event()
        self._release = threading.Event()
        self._thread = threading.Thread(target=self._run)

    def _run(self) -> None:
        with gate.hold_node_http(self._key):
            self._held.set()
            self._release.wait(timeout=5)

    def __enter__(self) -> _Holder:
        self._thread.start()
        assert self._held.wait(timeout=2)
        return self

    def __exit__(self, *exc_info) -> None:
        self._release.set()
        self._thread.join(timeout=5)


def test_hold_serializes_two_threads():
    key = "10.0.0.1:9100"
    order: list[str] = []
    barrier = threading.Barrier(2)

    def worker(name: str, hold: float) -> None:
        barrier.wait()
        with gate.hold_node_http(key):
            order.append(f"{name}-enter")
            time.sleep(hold)
            order.append(f"{name}-exit")

    t1 = threading.Thread(target=worker, args=("a", 0.05))
    t2 = threading.Thread(target=worker, args=("b", 0.01))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    # Second must not enter until first exits.
    assert order.index("a-exit") < order.index("b-enter") or order.index("b-exit") < order.index(
        "a-enter"
    )


def test_nonblocking_raises_when_slot_held():
    key = "10.0.0.2:9100"
    with _Holder(key):
        with gate.node_http_gate_nonblocking():
            with pytest.raises(gate.NodeHttpBusy):
                with gate.hold_node_http(key):
                    pass


def test_interactive_wait_is_bounded(monkeypatch):
    key = "10.0.0.4:9100"
    monkeypatch.setattr(gate, "WAIT_TIMEOUT_SECONDS", 0.1)
    with _Holder(key):
        started = time.monotonic()
        with pytest.raises(gate.NodeHttpTimeout):
            with gate.hold_node_http(key):
                pass
        assert time.monotonic() - started < 1.0


def test_bypass_skips_held_slot():
    key = "10.0.0.5:9100"
    with _Holder(key):
        with gate.node_http_gate_bypass():
            with gate.hold_node_http(key):
                pass


def test_same_thread_reentrant():
    key = "10.0.0.3:9100"
    with gate.hold_node_http(key):
        with gate.hold_node_http(key):
            pass


def test_remote_adapter_request_uses_gate(monkeypatch):
    adapter, client = _adapter(monkeypatch)

    with _Holder(adapter._http_gate_key):
        with gate.node_http_gate_nonblocking():
            with pytest.raises(gate.NodeHttpBusy):
                adapter.health_check()
        assert client.calls == []

    assert adapter.health_check() == {"ok": True}
    assert len(client.calls) == 1


def test_adapter_reports_node_busy_when_wait_expires(monkeypatch):
    adapter, client = _adapter(monkeypatch)
    monkeypatch.setattr(gate, "WAIT_TIMEOUT_SECONDS", 0.1)

    with _Holder(adapter._http_gate_key):
        with pytest.raises(HTTPException) as excinfo:
            adapter.health_check()

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail["code"] == "node_busy"
    assert client.calls == []


def test_long_request_does_not_wait_for_slot(monkeypatch):
    adapter, client = _adapter(monkeypatch)

    with _Holder(adapter._http_gate_key):
        # Patch build / backup / config apply: minutes of work, never waits for the slot.
        assert adapter._request("POST", "/openvpn/patch", timeout=1800.0) == {"ok": True}

    assert len(client.calls) == 1
