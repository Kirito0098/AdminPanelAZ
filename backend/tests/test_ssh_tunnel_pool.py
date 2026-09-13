from __future__ import annotations

import json
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
        host, *, port, username, client_keys, client_factory, server_host_key_algs, known_hosts
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
        host, *, port, username, client_keys, client_factory, server_host_key_algs, known_hosts
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
        host, *, port, username, client_keys, client_factory, server_host_key_algs, known_hosts
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
