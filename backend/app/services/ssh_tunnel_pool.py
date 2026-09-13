"""Reusable SSH local-forward pool for node agents."""

from __future__ import annotations

import atexit
import asyncio
import logging
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any

import asyncssh

from app.config import get_settings
from app.services.crypto import decrypt_secret
from app.services.node_link_errors import CODE_SSH_AUTH, CODE_SSH_TUNNEL, CODE_SSH_UNREACHABLE

logger = logging.getLogger(__name__)

DEFAULT_IDLE_TIMEOUT_SECONDS = 600.0
DEFAULT_OPERATION_TIMEOUT_SECONDS = 30.0
DEFAULT_CLEANUP_INTERVAL_SECONDS = 30.0
_LOOP_START_TIMEOUT_SECONDS = 5.0


class SshTunnelError(ValueError):
    """Stable SSH transport failure with a link-error compatible code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class _TunnelSession:
    signature: tuple[Any, ...]
    connection: Any
    listener: Any
    local_port: int
    last_used: float


class SshTunnelPool:
    def __init__(
        self,
        *,
        idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
        cleanup_interval_seconds: float = DEFAULT_CLEANUP_INTERVAL_SECONDS,
        time_fn=time.monotonic,
        start_cleaner: bool = True,
    ) -> None:
        self._idle_timeout_seconds = max(0.0, float(idle_timeout_seconds))
        self._operation_timeout_seconds = max(1.0, float(operation_timeout_seconds))
        self._cleanup_interval_seconds = max(1.0, float(cleanup_interval_seconds))
        self._time = time_fn
        self._lock = threading.RLock()
        self._sessions: dict[int, _TunnelSession] = {}
        self._closed = False

        self._loop = asyncio.new_event_loop()
        self._loop_ready = threading.Event()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name="ssh-tunnel-pool-loop",
            daemon=True,
        )
        self._loop_thread.start()
        if not self._loop_ready.wait(timeout=_LOOP_START_TIMEOUT_SECONDS):
            raise RuntimeError("SSH tunnel event loop did not start")

        self._cleaner_stop = threading.Event()
        self._cleaner_thread: threading.Thread | None = None
        if start_cleaner:
            self._cleaner_thread = threading.Thread(
                target=self._run_cleaner,
                name="ssh-tunnel-pool-cleaner",
                daemon=True,
            )
            self._cleaner_thread.start()

    def ensure(self, node: Any) -> int:
        now = self._time()
        signature = self._node_signature(node)
        with self._lock:
            self._assert_open()
            self._expire_idle_sessions_locked(now)
            current = self._sessions.get(int(node.id))
            if current and current.signature == signature:
                current.last_used = now
                return current.local_port
            if current:
                self._close_session_locked(int(node.id), current)
            session = self._run_coroutine(
                self._open_session(node=node, signature=signature, now=now),
                timeout=self._operation_timeout_seconds,
            )
            self._sessions[int(node.id)] = session
            return session.local_port

    def drop(self, node_id: int) -> None:
        with self._lock:
            session = self._sessions.pop(int(node_id), None)
            if session is None:
                return
            self._close_session_noexcept(session)

    def drop_all(self) -> None:
        with self._lock:
            for node_id in list(self._sessions):
                session = self._sessions.pop(node_id)
                self._close_session_noexcept(session)

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._cleaner_stop.set()
        if self._cleaner_thread is not None:
            self._cleaner_thread.join(timeout=1.0)
        self.drop_all()
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop_thread.join(timeout=1.0)

    def _assert_open(self) -> None:
        if self._closed:
            raise RuntimeError("SSH tunnel pool is shut down")

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        try:
            self._loop.run_forever()
        finally:
            pending = [task for task in asyncio.all_tasks(self._loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()

    def _run_cleaner(self) -> None:
        while not self._cleaner_stop.wait(self._cleanup_interval_seconds):
            try:
                with self._lock:
                    if self._closed:
                        return
                    self._expire_idle_sessions_locked(self._time())
            except Exception:
                logger.debug("SSH tunnel idle cleanup failed", exc_info=True)

    def _expire_idle_sessions_locked(self, now: float) -> None:
        if self._idle_timeout_seconds <= 0:
            return
        cutoff = now - self._idle_timeout_seconds
        expired = [
            (node_id, session)
            for node_id, session in self._sessions.items()
            if session.last_used <= cutoff
        ]
        for node_id, session in expired:
            self._close_session_locked(node_id, session)

    def _close_session_locked(self, node_id: int, session: _TunnelSession) -> None:
        self._sessions.pop(node_id, None)
        self._close_session_noexcept(session)

    def _close_session_noexcept(self, session: _TunnelSession) -> None:
        try:
            self._run_coroutine(
                self._close_session_async(session),
                timeout=self._operation_timeout_seconds,
            )
        except Exception:
            logger.debug("Failed to close SSH tunnel session cleanly", exc_info=True)

    def _run_coroutine(self, coro: Any, *, timeout: float) -> Any:
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        except RuntimeError as exc:
            raise RuntimeError("SSH tunnel event loop is unavailable") from exc
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise SshTunnelError(
                CODE_SSH_UNREACHABLE,
                "SSH tunnel operation timed out",
            ) from exc

    async def _open_session(self, *, node: Any, signature: tuple[Any, ...], now: float) -> _TunnelSession:
        host = str(getattr(node, "ssh_host", "") or "").strip()
        username = str(getattr(node, "ssh_username", "") or "").strip()
        port = int(getattr(node, "ssh_port", 22) or 22)
        remote_host = str(getattr(node, "ssh_remote_agent_host", "") or "127.0.0.1").strip()
        remote_port = int(getattr(node, "ssh_remote_agent_port", None) or getattr(node, "port", 0) or 0)
        key = self._decrypt_credential(getattr(node, "ssh_private_key_encrypted", ""), required=True)
        passphrase = self._decrypt_credential(getattr(node, "ssh_passphrase_encrypted", ""), required=False)

        if not host or not username:
            raise SshTunnelError(CODE_SSH_AUTH, "SSH host or username is not configured")
        if remote_port <= 0:
            raise SshTunnelError(CODE_SSH_TUNNEL, "SSH remote agent port is not configured")

        try:
            client_key = asyncssh.import_private_key(key, passphrase=passphrase or None)
        except Exception as exc:
            raise SshTunnelError(
                CODE_SSH_AUTH,
                "SSH private key or passphrase is invalid",
            ) from exc

        connection = None
        try:
            connection = await asyncssh.connect(
                host,
                port=port,
                username=username,
                client_keys=[client_key],
                known_hosts=None,
            )
            listener = await connection.forward_local("127.0.0.1", 0, remote_host, remote_port)
            local_port = int(listener.get_port())
            return _TunnelSession(
                signature=signature,
                connection=connection,
                listener=listener,
                local_port=local_port,
                last_used=now,
            )
        except asyncssh.PermissionDenied as exc:
            if connection is not None:
                await self._close_connection_only(connection)
            raise SshTunnelError(CODE_SSH_AUTH, f"SSH authentication failed: {exc}") from exc
        except (asyncssh.ConnectionLost, asyncssh.DisconnectError, OSError, asyncio.TimeoutError) as exc:
            if connection is not None:
                await self._close_connection_only(connection)
            raise SshTunnelError(CODE_SSH_UNREACHABLE, f"SSH host is unreachable: {exc}") from exc
        except Exception as exc:
            if connection is not None:
                await self._close_connection_only(connection)
            raise SshTunnelError(CODE_SSH_TUNNEL, f"SSH tunnel setup failed: {exc}") from exc

    async def _close_session_async(self, session: _TunnelSession) -> None:
        try:
            session.listener.close()
        finally:
            await self._maybe_wait_closed(session.listener)
        await self._close_connection_only(session.connection)

    async def _close_connection_only(self, connection: Any) -> None:
        try:
            connection.close()
        finally:
            await self._maybe_wait_closed(connection)

    async def _maybe_wait_closed(self, obj: Any) -> None:
        waiter = getattr(obj, "wait_closed", None)
        if waiter is None:
            return
        result = waiter()
        if asyncio.iscoroutine(result):
            await result

    def _decrypt_credential(self, encrypted: str, *, required: bool) -> str:
        text = str(encrypted or "").strip()
        if not text:
            if required:
                raise SshTunnelError(CODE_SSH_AUTH, "SSH private key is not configured")
            return ""
        try:
            return decrypt_secret(text, get_settings().secret_key)
        except Exception as exc:
            code = CODE_SSH_AUTH if required else CODE_SSH_TUNNEL
            raise SshTunnelError(code, "Failed to decrypt SSH credentials") from exc

    def _node_signature(self, node: Any) -> tuple[Any, ...]:
        return (
            str(getattr(node, "ssh_host", "") or "").strip(),
            int(getattr(node, "ssh_port", 22) or 22),
            str(getattr(node, "ssh_username", "") or "").strip(),
            str(getattr(node, "ssh_private_key_encrypted", "") or ""),
            str(getattr(node, "ssh_passphrase_encrypted", "") or ""),
            str(getattr(node, "ssh_remote_agent_host", "") or "127.0.0.1").strip(),
            int(getattr(node, "ssh_remote_agent_port", None) or getattr(node, "port", 0) or 0),
        )


_pool_singleton: SshTunnelPool | None = None
_pool_singleton_lock = threading.Lock()


def get_ssh_tunnel_pool() -> SshTunnelPool:
    global _pool_singleton
    with _pool_singleton_lock:
        if _pool_singleton is None:
            _pool_singleton = SshTunnelPool()
        return _pool_singleton


def _shutdown_singleton() -> None:
    global _pool_singleton
    with _pool_singleton_lock:
        pool = _pool_singleton
        _pool_singleton = None
    if pool is not None:
        pool.shutdown()


atexit.register(_shutdown_singleton)
