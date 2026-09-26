from __future__ import annotations

import asyncio
import json
import threading
import time
from types import SimpleNamespace

import asyncssh
import pytest

from app.services.crypto import encrypt_secret
from app.services.ssh_tunnel_pool import EnsureResult, SshTunnelError, SshTunnelPool


class _FakeListener:
    def __init__(self, port: int):
        self._port = port
        self.closed = False
        self.wait_closed_calls = 0

    def get_port(self) -> int:
        return self._port

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.wait_closed_calls += 1


class _FakeConnection:
    def __init__(self, port: int):
        self.listener = _FakeListener(port)
        self.closed = False
        self.wait_closed_calls = 0
        self.forward_calls: list[tuple[str, int, str, int]] = []

    async def forward_local(self, host: str, port: int, remote_host: str, remote_port: int):
        self.forward_calls.append((host, port, remote_host, remote_port))
        return self.listener

    def close(self) -> None:
        self.closed = True

    def is_closed(self) -> bool:
        return self.closed

    async def wait_closed(self) -> None:
        self.wait_closed_calls += 1


class _FakeHostKey:
    def __init__(self, exported: str):
        self._exported = exported

    def export_public_key(self) -> bytes:
        return self._exported.encode("utf-8")


def _node(secret_key: str, **overrides):
    return SimpleNamespace(
        id=overrides.pop("id", 7),
        port=overrides.pop("port", 9100),
        ssh_host=overrides.pop("ssh_host", "203.0.113.10"),
        ssh_port=overrides.pop("ssh_port", 22),
        ssh_username=overrides.pop("ssh_username", "root"),
        ssh_private_key_encrypted=overrides.pop(
            "ssh_private_key_encrypted",
            encrypt_secret("PRIVATE KEY", secret_key),
        ),
        ssh_passphrase_encrypted=overrides.pop("ssh_passphrase_encrypted", ""),
        ssh_remote_agent_host=overrides.pop("ssh_remote_agent_host", "127.0.0.1"),
        ssh_remote_agent_port=overrides.pop("ssh_remote_agent_port", None),
        ssh_host_key=overrides.pop("ssh_host_key", ""),
        node_metadata=overrides.pop("node_metadata", "{}"),
        **overrides,
    )


def test_ensure_returns_discovered_host_key_and_reuses_tunnel(monkeypatch):
    secret_key = "test-secret-key"
    imported_keys: list[tuple[str, str | None]] = []
    connections: list[_FakeConnection] = []
    discovered: list[tuple[str, int]] = []
    discovered_key = _FakeHostKey("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFirstKey")

    async def _fake_get_server_host_key(host, *, port):
        discovered.append((host, port))
        return discovered_key

    async def _fake_connect(
        host, *, port, username, client_keys, client_factory, server_host_key_algs, known_hosts, **_options
    ):
        assert host == "203.0.113.10"
        assert port == 22
        assert username == "root"
        assert client_keys == ["parsed-key"]
        assert server_host_key_algs == "default"
        assert known_hosts == ([], [], [])
        assert client_factory().validate_host_public_key(host, host, port, discovered_key) is True
        conn = _FakeConnection(45123)
        connections.append(conn)
        return conn

    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.get_settings",
        lambda: SimpleNamespace(secret_key=secret_key),
    )
    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.asyncssh.import_private_key",
        lambda key, passphrase=None: imported_keys.append((key, passphrase)) or "parsed-key",
    )
    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.get_server_host_key", _fake_get_server_host_key)
    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.connect", _fake_connect)

    pool = SshTunnelPool(start_cleaner=False)
    node = _node(secret_key)
    try:
        first = pool.ensure(node)
        second = pool.ensure(node)
    finally:
        pool.shutdown()

    assert first == EnsureResult(
        local_port=45123,
        discovered_host_key_text="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFirstKey",
    )
    assert second == EnsureResult(local_port=45123)
    assert imported_keys == [("PRIVATE KEY", None)]
    assert discovered == [("203.0.113.10", 22)]
    assert len(connections) == 1
    assert connections[0].forward_calls == [("127.0.0.1", 0, "127.0.0.1", 9100)]
    assert json.loads(node.node_metadata) == {}


def test_drop_closes_session(monkeypatch):
    secret_key = "test-secret-key"
    connection = _FakeConnection(45124)
    discovered_key = _FakeHostKey("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIStoredKey")

    async def _fake_connect(*args, client_factory, server_host_key_algs, known_hosts, **kwargs):
        assert server_host_key_algs == "default"
        assert known_hosts == ([], [], [])
        assert client_factory().validate_host_public_key("203.0.113.10", "203.0.113.10", 22, discovered_key) is True
        return connection

    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.get_settings",
        lambda: SimpleNamespace(secret_key=secret_key),
    )
    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.asyncssh.import_private_key",
        lambda key, passphrase=None: "parsed-key",
    )

    async def _fake_get_server_host_key(*args, **kwargs):
        return discovered_key

    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.get_server_host_key", _fake_get_server_host_key)
    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.connect", _fake_connect)

    pool = SshTunnelPool(start_cleaner=False)
    node = _node(secret_key, id=8)
    try:
        assert pool.ensure(node).local_port == 45124
        pool.drop(node.id)
    finally:
        pool.shutdown()

    assert connection.listener.closed is True
    assert connection.listener.wait_closed_calls == 1
    assert connection.closed is True
    assert connection.wait_closed_calls == 1


def test_ensure_uses_stored_host_key_without_refetch(monkeypatch):
    secret_key = "test-secret-key"
    stored_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIStoredKey"
    imported_public_keys: list[str] = []

    async def _fake_connect(
        host, *, port, username, client_keys, client_factory, server_host_key_algs, known_hosts, **_options
    ):
        assert host == "203.0.113.10"
        assert port == 22
        assert username == "root"
        assert client_keys == ["parsed-key"]
        assert server_host_key_algs == "default"
        assert known_hosts == ([], [], [])
        presented_key = _FakeHostKey(stored_key)
        assert client_factory().validate_host_public_key(host, host, port, presented_key) is True
        return _FakeConnection(45125)

    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.get_settings",
        lambda: SimpleNamespace(secret_key=secret_key),
    )
    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.asyncssh.import_private_key",
        lambda key, passphrase=None: "parsed-key",
    )
    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.asyncssh.import_public_key",
        lambda data: imported_public_keys.append(data) or _FakeHostKey(data),
    )

    async def _unexpected_discovery(*args, **kwargs):
        raise AssertionError("get_server_host_key should not be called when ssh_host_key is already stored")

    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.get_server_host_key", _unexpected_discovery)
    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.connect", _fake_connect)

    pool = SshTunnelPool(start_cleaner=False)
    node = _node(secret_key, ssh_host_key=stored_key)
    try:
        assert pool.ensure(node) == EnsureResult(local_port=45125)
    finally:
        pool.shutdown()

    assert imported_public_keys == [stored_key]
    assert node.ssh_host_key == stored_key


def test_ensure_raises_auth_error_on_host_key_mismatch(monkeypatch):
    secret_key = "test-secret-key"
    stored_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIStoredKey"
    presented_key = _FakeHostKey("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDifferentKey")

    async def _fake_connect(
        host, *, port, username, client_keys, client_factory, server_host_key_algs, known_hosts, **_options
    ):
        assert server_host_key_algs == "default"
        assert known_hosts == ([], [], [])
        if not client_factory().validate_host_public_key(host, host, port, presented_key):
            raise asyncssh.HostKeyNotVerifiable("Host key is not trusted")
        raise AssertionError("connect should reject mismatched host key")

    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.get_settings",
        lambda: SimpleNamespace(secret_key=secret_key),
    )
    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.asyncssh.import_private_key",
        lambda key, passphrase=None: "parsed-key",
    )
    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.asyncssh.import_public_key",
        lambda data: _FakeHostKey(data),
    )

    async def _unexpected_discovery(*args, **kwargs):
        raise AssertionError("get_server_host_key should not be called when ssh_host_key is already stored")

    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.get_server_host_key", _unexpected_discovery)
    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.connect", _fake_connect)

    pool = SshTunnelPool(start_cleaner=False)
    node = _node(secret_key, ssh_host_key=stored_key)
    try:
        with pytest.raises(SshTunnelError) as exc:
            pool.ensure(node)
    finally:
        pool.shutdown()

    assert exc.value.code == "node_ssh_auth"
    assert "host key verification failed" in str(exc.value).lower()


def test_store_expected_host_key_text_updates_column_once():
    node = _node("test-secret-key")

    changed = SshTunnelPool.store_expected_host_key_text(node, "ssh-ed25519 AAAAC3NzaStored")
    unchanged = SshTunnelPool.store_expected_host_key_text(node, "ssh-ed25519 AAAAC3NzaStored")

    assert changed is True
    assert unchanged is False
    assert node.ssh_host_key == "ssh-ed25519 AAAAC3NzaStored"


def test_stored_host_key_falls_back_to_metadata_legacy():
    pool = SshTunnelPool(start_cleaner=False)
    try:
        node = _node(
            "test-secret-key",
            ssh_host_key="",
            node_metadata=json.dumps({"ssh_host_key": "ssh-ed25519 AAAAC3NzaLegacy"}),
        )
        assert pool._stored_host_key_text(node) == "ssh-ed25519 AAAAC3NzaLegacy"
    finally:
        pool.shutdown()


_STORED_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIStoredKey"


class _Nodes:
    """Pool wiring with a per-host connect behaviour (stored host key, no discovery)."""

    def __init__(self, monkeypatch, secret_key: str = "test-secret-key"):
        self.secret_key = secret_key
        self.connections: dict[str, list[_FakeConnection]] = {}
        self.connect_options: list[dict] = []
        self.behaviour: dict[str, object] = {}
        self._next_port = 46000
        monkeypatch.setattr(
            "app.services.ssh_tunnel_pool.get_settings",
            lambda: SimpleNamespace(secret_key=secret_key),
        )
        monkeypatch.setattr(
            "app.services.ssh_tunnel_pool.asyncssh.import_private_key",
            lambda key, passphrase=None: "parsed-key",
        )
        monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.import_public_key", _FakeHostKey)
        monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.connect", self._connect)

    async def _connect(self, host, **options):
        self.connect_options.append(options)
        behaviour = self.behaviour.get(host)
        if behaviour is not None:
            await behaviour()
        self._next_port += 1
        conn = _FakeConnection(self._next_port)
        self.connections.setdefault(host, []).append(conn)
        return conn

    def node(self, node_id: int, host: str):
        return _node(self.secret_key, id=node_id, ssh_host=host, ssh_host_key=_STORED_KEY)


def _blocking_until(release: threading.Event, started: threading.Event | None = None):
    async def _behaviour():
        if started is not None:
            started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)

    return _behaviour


def _in_thread(fn) -> tuple[threading.Thread, dict]:
    outcome: dict = {}

    def _run():
        try:
            outcome["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — surfaced by the test
            outcome["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread, outcome


def test_connect_enables_keepalive_and_connect_timeout(monkeypatch):
    nodes = _Nodes(monkeypatch)
    pool = SshTunnelPool(start_cleaner=False, operation_timeout_seconds=20)
    try:
        pool.ensure(nodes.node(1, "198.51.100.1"))
    finally:
        pool.shutdown()

    options = nodes.connect_options[0]
    assert options["keepalive_interval"] > 0
    assert options["keepalive_count_max"] >= 1
    assert options["keepalive_interval"] * options["keepalive_count_max"] <= 60
    assert 0 < options["connect_timeout"] <= 20


def test_dead_tunnel_is_replaced_instead_of_reused(monkeypatch):
    nodes = _Nodes(monkeypatch)
    pool = SshTunnelPool(start_cleaner=False)
    node = nodes.node(1, "198.51.100.1")
    try:
        first = pool.ensure(node)
        dead = nodes.connections["198.51.100.1"][0]
        dead.closed = True
        second = pool.ensure(node)
        third = pool.ensure(node)
    finally:
        pool.shutdown()

    assert len(nodes.connections["198.51.100.1"]) == 2
    assert second.local_port != first.local_port
    assert third.local_port == second.local_port
    assert dead.listener.closed is True


def test_hung_node_does_not_block_other_nodes(monkeypatch):
    nodes = _Nodes(monkeypatch)
    release, started = threading.Event(), threading.Event()
    nodes.behaviour["198.51.100.1"] = _blocking_until(release, started)
    pool = SshTunnelPool(start_cleaner=False)
    cached = nodes.node(2, "198.51.100.2")
    try:
        pool.ensure(cached)
        hung, _ = _in_thread(lambda: pool.ensure(nodes.node(1, "198.51.100.1")))
        assert started.wait(2)

        reuse, reuse_outcome = _in_thread(lambda: pool.ensure(cached))
        fresh, fresh_outcome = _in_thread(lambda: pool.ensure(nodes.node(3, "198.51.100.3")))
        reuse.join(2)
        fresh.join(2)
        reused, opened = dict(reuse_outcome), dict(fresh_outcome)
        still_hung = hung.is_alive()
    finally:
        release.set()
        hung.join(5)
        pool.shutdown()

    assert "value" in reused and "value" in opened
    assert still_hung is True


def test_concurrent_ensure_for_one_node_opens_a_single_tunnel(monkeypatch):
    nodes = _Nodes(monkeypatch)
    release, started = threading.Event(), threading.Event()
    nodes.behaviour["198.51.100.1"] = _blocking_until(release, started)
    pool = SshTunnelPool(start_cleaner=False)
    node = nodes.node(1, "198.51.100.1")
    try:
        first, first_outcome = _in_thread(lambda: pool.ensure(node))
        assert started.wait(2)
        second, second_outcome = _in_thread(lambda: pool.ensure(node))
        time.sleep(0.1)
        release.set()
        first.join(5)
        second.join(5)
    finally:
        pool.shutdown()

    assert len(nodes.connections["198.51.100.1"]) == 1
    assert first_outcome["value"].local_port == second_outcome["value"].local_port


def test_slow_close_does_not_block_other_nodes(monkeypatch):
    nodes = _Nodes(monkeypatch)
    pool = SshTunnelPool(start_cleaner=False)
    closing, cached = nodes.node(1, "198.51.100.1"), nodes.node(2, "198.51.100.2")
    release, started = threading.Event(), threading.Event()
    try:
        pool.ensure(closing)
        pool.ensure(cached)
        slow = nodes.connections["198.51.100.1"][0]

        async def _slow_wait_closed():
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.01)

        slow.wait_closed = _slow_wait_closed
        dropper, _ = _in_thread(lambda: pool.drop(closing.id))
        assert started.wait(2)
        reuse, reuse_outcome = _in_thread(lambda: pool.ensure(cached))
        reuse.join(2)
        reused = dict(reuse_outcome)
    finally:
        release.set()
        dropper.join(5)
        pool.shutdown()

    assert "value" in reused


def test_open_cancelled_by_timeout_closes_the_connection(monkeypatch):
    nodes = _Nodes(monkeypatch)
    release = threading.Event()
    pool = SshTunnelPool(start_cleaner=False, operation_timeout_seconds=1)
    node = nodes.node(1, "198.51.100.1")

    original_connect = nodes._connect

    async def _connect_then_hang_on_forward(host, **options):
        conn = await original_connect(host, **options)

        async def _hanging_forward(*_args):
            while not release.is_set():
                await asyncio.sleep(0.01)

        conn.forward_local = _hanging_forward
        return conn

    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.connect", _connect_then_hang_on_forward)
    try:
        with pytest.raises(SshTunnelError) as exc:
            pool.ensure(node)
        conn = nodes.connections["198.51.100.1"][0]
        deadline = time.monotonic() + 2
        while not conn.closed and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        release.set()
        pool.shutdown()

    assert exc.value.code == "node_ssh_unreachable"
    assert conn.closed is True


def test_expire_idle_closes_idle_and_dead_sessions_only(monkeypatch):
    nodes = _Nodes(monkeypatch)
    clock = [1000.0]
    pool = SshTunnelPool(start_cleaner=False, idle_timeout_seconds=600, time_fn=lambda: clock[0])
    idle, dead, busy = nodes.node(1, "198.51.100.1"), nodes.node(2, "198.51.100.2"), nodes.node(3, "198.51.100.3")
    try:
        pool.ensure(idle)
        clock[0] += 500
        pool.ensure(dead)
        pool.ensure(busy)
        clock[0] += 200
        nodes.connections["198.51.100.2"][0].closed = True
        pool.expire_idle()
        closed = {host: conns[0].listener.closed for host, conns in nodes.connections.items()}
        busy_port = pool.ensure(busy).local_port
    finally:
        pool.shutdown()

    assert closed == {"198.51.100.1": True, "198.51.100.2": True, "198.51.100.3": False}
    assert len(nodes.connections["198.51.100.3"]) == 1
    assert busy_port == nodes.connections["198.51.100.3"][0].listener.get_port()


def test_ensure_does_not_close_other_nodes_sessions(monkeypatch):
    nodes = _Nodes(monkeypatch)
    clock = [1000.0]
    pool = SshTunnelPool(start_cleaner=False, idle_timeout_seconds=600, time_fn=lambda: clock[0])
    try:
        pool.ensure(nodes.node(1, "198.51.100.1"))
        clock[0] += 700
        nodes.connections["198.51.100.1"][0].closed = False
        pool.ensure(nodes.node(2, "198.51.100.2"))
    finally:
        other_listener_closed = nodes.connections["198.51.100.1"][0].listener.closed
        pool.shutdown()

    assert other_listener_closed is False


def test_changed_ssh_settings_replace_and_close_the_old_tunnel(monkeypatch):
    nodes = _Nodes(monkeypatch)
    pool = SshTunnelPool(start_cleaner=False)
    node = nodes.node(1, "198.51.100.1")
    try:
        pool.ensure(node)
        node.ssh_port = 2222
        pool.ensure(node)
    finally:
        pool.shutdown()

    old, new = nodes.connections["198.51.100.1"]
    assert old.listener.closed is True and old.closed is True
    assert new.closed is True  # closed by shutdown, after being handed out


def test_hanging_close_is_bounded(monkeypatch):
    import app.services.ssh_tunnel_pool as pool_module

    monkeypatch.setattr(pool_module, "_CLOSE_TIMEOUT_SECONDS", 0.2)
    nodes = _Nodes(monkeypatch)
    pool = SshTunnelPool(start_cleaner=False, operation_timeout_seconds=30)
    node = nodes.node(1, "198.51.100.1")
    release = threading.Event()
    try:
        pool.ensure(node)
        nodes.connections["198.51.100.1"][0].wait_closed = _blocking_until(release)
        dropper, _ = _in_thread(lambda: pool.drop(node.id))
        dropper.join(2)
        finished = not dropper.is_alive()
    finally:
        release.set()
        pool.shutdown()

    assert finished is True


def test_session_opened_while_pool_shut_down_is_closed(monkeypatch):
    nodes = _Nodes(monkeypatch)
    pool = SshTunnelPool(start_cleaner=False)

    async def _shut_down_meanwhile():
        pool._closed = True

    nodes.behaviour["198.51.100.1"] = _shut_down_meanwhile
    try:
        with pytest.raises(RuntimeError, match="shut down"):
            pool.ensure(nodes.node(1, "198.51.100.1"))
    finally:
        pool._closed = False
        pool.shutdown()

    assert nodes.connections["198.51.100.1"][0].listener.closed is True
