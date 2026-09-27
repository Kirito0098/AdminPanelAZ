"""OpenVPN management socket: ``status`` reply ends at the ``END`` line, not at idle timeouts."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from app.services.openvpn_management import OpenVpnManagementService

BANNER = b">INFO:OpenVPN Management Interface Version 6 -- type 'help' for more info\r\n"
STATUS_REPLY = (
    b"TITLE\tOpenVPN 2.6.12\r\n"
    b"TIME\t2026-09-27 12:00:00\t1790510400\r\n"
    b"HEADER\tCLIENT_LIST\tCommon Name\tReal Address\r\n"
    b"CLIENT_LIST\talice\t203.0.113.5:51000\t10.29.0.2\t\t100\t200\t2026-09-27 11:00:00\t1790506800\tUNDEF\t0\t0\tAES-256-GCM\r\n"
    b"GLOBAL_STATS\tdco_enabled\t1\r\n"
    b"END\r\n"
)


def _serve_once(server: socket.socket, reply: bytes) -> None:
    conn, _ = server.accept()
    with conn:
        conn.sendall(BANNER)
        conn.recv(1024)
        conn.sendall(reply)
        # Like OpenVPN: keep the session open until the client sends ``quit``.
        conn.settimeout(5)
        try:
            while conn.recv(1024):
                conn.close()
                return
        except OSError:
            return


@pytest.fixture
def management_socket(tmp_path):
    path = tmp_path / "vpn-udp.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)

    def start(reply: bytes) -> threading.Thread:
        thread = threading.Thread(target=_serve_once, args=(server, reply), daemon=True)
        thread.start()
        return thread

    yield path, start
    server.close()


@pytest.mark.parametrize("reply", [STATUS_REPLY, STATUS_REPLY.replace(b"\r\n", b"\n")])
def test_status_read_stops_at_end_line(management_socket, reply):
    path, start = management_socket
    thread = start(reply)
    svc = OpenVpnManagementService(openvpn_socket_timeout=2.5, openvpn_socket_idle_timeout=1.0)

    started = time.monotonic()
    raw = svc.query_openvpn_management_socket(path, "status 3")
    elapsed = time.monotonic() - started
    thread.join(timeout=5)

    assert "CLIENT_LIST\talice" in raw
    assert svc.extract_status_payload_from_management(raw).endswith("END")
    assert elapsed < 0.9, f"waited for idle timeouts after END ({elapsed:.2f}s)"
