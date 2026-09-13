from __future__ import annotations

from types import SimpleNamespace

from app.services.crypto import encrypt_secret
from app.services.ssh_tunnel_pool import SshTunnelPool


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
        **overrides,
    )


def test_ensure_returns_stable_local_port(monkeypatch):
    secret_key = "test-secret-key"
    imported_keys: list[tuple[str, str | None]] = []
    connections: list[_FakeConnection] = []

    async def _fake_connect(host, *, port, username, client_keys, known_hosts):
        assert host == "203.0.113.10"
        assert port == 22
        assert username == "root"
        assert known_hosts is None
        assert client_keys == ["parsed-key"]
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
    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.connect", _fake_connect)

    pool = SshTunnelPool(start_cleaner=False)
    node = _node(secret_key)
    try:
        first = pool.ensure(node)
        second = pool.ensure(node)
    finally:
        pool.shutdown()

    assert first == 45123
    assert second == 45123
    assert imported_keys == [("PRIVATE KEY", None)]
    assert len(connections) == 1
    assert connections[0].forward_calls == [("127.0.0.1", 0, "127.0.0.1", 9100)]


def test_drop_closes_session(monkeypatch):
    secret_key = "test-secret-key"
    connection = _FakeConnection(45124)

    async def _fake_connect(*args, **kwargs):
        return connection

    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.get_settings",
        lambda: SimpleNamespace(secret_key=secret_key),
    )
    monkeypatch.setattr(
        "app.services.ssh_tunnel_pool.asyncssh.import_private_key",
        lambda key, passphrase=None: "parsed-key",
    )
    monkeypatch.setattr("app.services.ssh_tunnel_pool.asyncssh.connect", _fake_connect)

    pool = SshTunnelPool(start_cleaner=False)
    node = _node(secret_key, id=8)
    try:
        assert pool.ensure(node) == 45124
        pool.drop(node.id)
    finally:
        pool.shutdown()

    assert connection.listener.closed is True
    assert connection.listener.wait_closed_calls == 1
    assert connection.closed is True
    assert connection.wait_closed_calls == 1
