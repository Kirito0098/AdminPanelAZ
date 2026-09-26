"""HA PKI sync restarts replica OpenVPN servers only when the server identity changes.

Servers load ``ca``/``cert``/``key`` at start and re-read ``crl-verify`` on every new
connection, so client create/renew/delete must not drop every session on replicas.
"""

from __future__ import annotations

import io
import tarfile
from unittest.mock import MagicMock

import pytest

from app.services.node_sync import openvpn_pki_state, vpn_state_sync
from app.services.node_sync.openvpn_restart import OPENVPN_SERVER_UNITS
from app.services.openvpn_pki import ProfileValidationResult

_RESTART_OK = {"success": True, "restarted": list(OPENVPN_SERVER_UNITS), "skipped": [], "failed": []}


def _row(status: str, serial: str, name: str) -> str:
    revoked = "260901000000Z" if status == "R" else ""
    return f"{status}\t360101000000Z\t{revoked}\t{serial}\tunknown\t/CN={name}\n"


def _pki_archive(
    *,
    ca: bytes = b"ca-1",
    server_crt: bytes | None = b"server-crt-1",
    server_key: bytes = b"server-key-1",
    rows: tuple[str, ...] = (),
) -> bytes:
    files = {
        "easyrsa3/pki/ca.crt": ca,
        "easyrsa3/pki/private/antizapret-server.key": server_key,
        "easyrsa3/pki/crl.pem": b"crl",
        "easyrsa3/pki/index.txt": "".join(rows).encode(),
    }
    if server_crt is not None:
        files["easyrsa3/pki/issued/antizapret-server.crt"] = server_crt
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


_BASE_ROWS = (_row("V", "0A", "alice"), _row("R", "0B", "old-revoked"))


@pytest.fixture
def restart(monkeypatch) -> MagicMock:
    mock = MagicMock(return_value=dict(_RESTART_OK))
    monkeypatch.setattr(vpn_state_sync, "restart_all_openvpn_servers", mock)
    monkeypatch.setattr(vpn_state_sync, "copy_openvpn_profiles_from_primary", MagicMock())
    monkeypatch.setattr(
        vpn_state_sync, "validate_all_openvpn_profiles", lambda _adapter: ProfileValidationResult(ready=True, issues=())
    )
    return mock


def _adapters(before: bytes, after: bytes) -> tuple[MagicMock, MagicMock]:
    primary = MagicMock(name="primary")
    primary.export_easyrsa3_archive.return_value = after
    replica = MagicMock(name="replica")
    replica.export_easyrsa3_archive.return_value = before
    replica.kill_openvpn_client.return_value = {"success": True}
    return primary, replica


def _killed(replica: MagicMock) -> list[tuple[str, str]]:
    return [call.args for call in replica.kill_openvpn_client.call_args_list]


def test_new_client_does_not_restart_or_disconnect(restart):
    primary, replica = _adapters(
        _pki_archive(rows=_BASE_ROWS),
        _pki_archive(rows=(*_BASE_ROWS, _row("V", "0C", "bob"))),
    )

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    replica.import_easyrsa3_archive.assert_called_once_with(primary.export_easyrsa3_archive.return_value)
    restart.assert_not_called()
    assert _killed(replica) == []


def test_replica_state_is_read_before_the_import(restart):
    primary, replica = _adapters(_pki_archive(), _pki_archive())
    order: list[str] = []
    replica.export_easyrsa3_archive.side_effect = lambda: order.append("export") or _pki_archive()
    replica.import_easyrsa3_archive.side_effect = lambda _data: order.append("import")

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    assert order == ["export", "import"]


def test_deleted_client_is_disconnected_on_every_server_without_restart(restart):
    primary, replica = _adapters(
        _pki_archive(rows=(*_BASE_ROWS, _row("V", "0C", "bob"))),
        _pki_archive(rows=(*_BASE_ROWS, _row("R", "0C", "bob"))),
    )

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    restart.assert_not_called()
    assert _killed(replica) == [(unit, "bob") for unit in OPENVPN_SERVER_UNITS]


def test_client_revoked_and_recreated_in_between_is_not_disconnected(restart):
    primary, replica = _adapters(
        _pki_archive(rows=(*_BASE_ROWS, _row("V", "0C", "bob"))),
        _pki_archive(rows=(*_BASE_ROWS, _row("R", "0C", "bob"), _row("V", "0D", "bob"))),
    )

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    restart.assert_not_called()
    assert _killed(replica) == []


def test_renewed_client_does_not_restart(restart):
    primary, replica = _adapters(
        _pki_archive(rows=_BASE_ROWS),
        _pki_archive(rows=(*_BASE_ROWS, _row("V", "0E", "alice"))),
    )

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    restart.assert_not_called()
    assert _killed(replica) == []


@pytest.mark.parametrize(
    "after",
    [
        pytest.param({"ca": b"ca-2"}, id="ca"),
        pytest.param({"server_crt": b"server-crt-2"}, id="server-cert"),
        pytest.param({"server_key": b"server-key-2"}, id="server-key"),
        pytest.param({"server_crt": None}, id="server-cert-missing"),
    ],
)
def test_changed_server_identity_restarts(restart, after):
    primary, replica = _adapters(
        _pki_archive(rows=(*_BASE_ROWS, _row("V", "0C", "bob"))),
        _pki_archive(rows=(*_BASE_ROWS, _row("R", "0C", "bob")), **after),
    )

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    restart.assert_called_once_with(replica)
    assert _killed(replica) == []


@pytest.mark.parametrize(
    "before",
    [
        pytest.param(RuntimeError("replica export failed"), id="export-error"),
        pytest.param(b"not-a-tar", id="garbage"),
        pytest.param(b"", id="empty"),
    ],
)
def test_unknown_replica_state_restarts(restart, before):
    primary, replica = _adapters(b"", _pki_archive())
    if isinstance(before, Exception):
        replica.export_easyrsa3_archive.side_effect = before
    else:
        replica.export_easyrsa3_archive.return_value = before

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    replica.import_easyrsa3_archive.assert_called_once()
    restart.assert_called_once_with(replica)


def test_multihome_is_ensured_only_when_restart_is_needed(restart, monkeypatch):
    import app.services.openvpn_multihome as multihome

    ensure = MagicMock(return_value={"restart": dict(_RESTART_OK)})
    monkeypatch.setattr(multihome, "maybe_ensure_openvpn_multihome", ensure)

    primary, replica = _adapters(_pki_archive(), _pki_archive())
    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica, openvpn_multihome=True)
    ensure.assert_not_called()

    primary, replica = _adapters(_pki_archive(), _pki_archive(ca=b"ca-2"))
    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica, openvpn_multihome=True)
    ensure.assert_called_once_with(replica, enabled=True)
    restart.assert_not_called()


def _revoke_bob_and_carol() -> tuple[bytes, bytes]:
    return (
        _pki_archive(rows=(*_BASE_ROWS, _row("V", "0C", "bob"), _row("V", "0D", "carol"))),
        _pki_archive(rows=(*_BASE_ROWS, _row("R", "0C", "bob"), _row("R", "0D", "carol"))),
    )


def _kill_fails_on_first_unit(unit, _name):
    if unit == OPENVPN_SERVER_UNITS[0]:
        raise RuntimeError("404 Not Found")
    return {"success": True}


def test_old_agent_without_per_unit_kill_falls_back_to_disconnect(restart):
    primary, replica = _adapters(*_revoke_bob_and_carol())
    replica.kill_openvpn_client.side_effect = _kill_fails_on_first_unit

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    assert len(_killed(replica)) == 2 * len(OPENVPN_SERVER_UNITS)
    assert [call.args for call in replica.disconnect_openvpn_client.call_args_list] == [("bob",), ("carol",)]
    restart.assert_not_called()


def test_disconnect_failure_is_reported_after_trying_every_client(restart):
    primary, replica = _adapters(*_revoke_bob_and_carol())
    replica.kill_openvpn_client.side_effect = _kill_fails_on_first_unit
    replica.disconnect_openvpn_client.side_effect = lambda name: (_ for _ in ()).throw(
        RuntimeError(f"agent timeout for {name}")
    )

    with pytest.raises(RuntimeError, match=r"bob: .*404 Not Found.*agent timeout for bob.*carol: "):
        vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    assert len(_killed(replica)) == 2 * len(OPENVPN_SERVER_UNITS)
    restart.assert_not_called()


def test_successful_kill_does_not_call_disconnect(restart):
    primary, replica = _adapters(*_revoke_bob_and_carol())

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    replica.disconnect_openvpn_client.assert_not_called()


def _connected(*names: str) -> list[MagicMock]:
    clients = []
    for name in names:
        client = MagicMock()
        client.common_name = name
        clients.append(client)
    return clients


def _stateful_replica(before: bytes, after: bytes) -> tuple[MagicMock, MagicMock]:
    primary, replica = _adapters(before, after)
    state = {"archive": before}
    replica.export_easyrsa3_archive.side_effect = lambda: state["archive"]
    replica.import_easyrsa3_archive.side_effect = lambda data: state.update(archive=data)
    return primary, replica


@pytest.mark.parametrize("failing_step", ["profiles", "disconnect"])
def test_retry_after_failure_past_import_disconnects_connected_revoked_client(restart, monkeypatch, failing_step):
    primary, replica = _stateful_replica(
        _pki_archive(rows=(*_BASE_ROWS, _row("V", "0C", "bob"))),
        _pki_archive(rows=(*_BASE_ROWS, _row("R", "0C", "bob"))),
    )
    replica.parse_openvpn_status.return_value = _connected("alice", "bob", "old-revoked")
    copy_profiles = MagicMock(side_effect=RuntimeError("no space left on device"))
    if failing_step == "profiles":
        monkeypatch.setattr(vpn_state_sync, "copy_openvpn_profiles_from_primary", copy_profiles)
    else:
        replica.kill_openvpn_client.side_effect = RuntimeError("agent timeout")
        replica.disconnect_openvpn_client.side_effect = RuntimeError("agent timeout")

    with pytest.raises(RuntimeError):
        vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    copy_profiles.side_effect = None
    replica.kill_openvpn_client.reset_mock(side_effect=True)
    replica.kill_openvpn_client.return_value = {"success": True}
    replica.disconnect_openvpn_client.side_effect = None
    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    assert _killed(replica) == [(unit, name) for name in ("bob", "old-revoked") for unit in OPENVPN_SERVER_UNITS]
    restart.assert_not_called()


def test_status_is_not_read_without_revoked_clients(restart):
    rows = (_row("V", "0A", "alice"),)
    primary, replica = _adapters(_pki_archive(rows=rows), _pki_archive(rows=rows))

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    replica.parse_openvpn_status.assert_not_called()


def test_revoked_clients_not_connected_are_not_disconnected(restart):
    primary, replica = _adapters(_pki_archive(rows=_BASE_ROWS), _pki_archive(rows=_BASE_ROWS))
    replica.parse_openvpn_status.return_value = _connected("alice")

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    assert _killed(replica) == []


def test_revoked_client_with_new_certificate_is_not_disconnected(restart):
    rows = (*_BASE_ROWS, _row("R", "0C", "bob"), _row("V", "0D", "bob"))
    primary, replica = _adapters(_pki_archive(rows=rows), _pki_archive(rows=rows))
    replica.parse_openvpn_status.return_value = _connected("bob")

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    assert _killed(replica) == []


def test_unreadable_status_still_disconnects_newly_revoked(restart):
    primary, replica = _adapters(
        _pki_archive(rows=(*_BASE_ROWS, _row("V", "0C", "bob"))),
        _pki_archive(rows=(*_BASE_ROWS, _row("R", "0C", "bob"))),
    )
    replica.parse_openvpn_status.side_effect = RuntimeError("monitoring unavailable")

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    assert _killed(replica) == [(unit, "bob") for unit in OPENVPN_SERVER_UNITS]


def test_read_pki_state_accepts_dot_slash_members():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in {
            "./easyrsa3/pki/ca.crt": b"ca",
            "./easyrsa3/pki/issued/antizapret-server.crt": b"crt",
            "./easyrsa3/pki/private/antizapret-server.key": b"key",
            "./easyrsa3/pki/index.txt": _row("R", "01", "bob").encode(),
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

    state = openvpn_pki_state.read_pki_state(buffer.getvalue())

    assert state is not None
    assert len(state.server_identity) == 3
    assert openvpn_pki_state.newly_revoked_clients(
        openvpn_pki_state.read_pki_state(_pki_archive()), state
    ) == ["bob"]


def test_server_identity_missing_on_both_sides_restarts(restart):
    primary, replica = _adapters(_pki_archive(server_crt=None), _pki_archive(server_crt=None))

    vpn_state_sync.sync_openvpn_pki_from_primary(primary, replica)

    restart.assert_called_once_with(replica)


@pytest.mark.parametrize(
    "payload",
    [b"", b"not-a-tar", _pki_archive()[:40], None, MagicMock()],
    ids=["empty", "garbage", "truncated", "none", "mock"],
)
def test_read_pki_state_rejects_unreadable_payloads(payload):
    assert openvpn_pki_state.read_pki_state(payload) is None


def test_newly_revoked_clients_without_prior_state_is_empty():
    after = openvpn_pki_state.read_pki_state(_pki_archive(rows=(_row("R", "01", "bob"),)))

    assert openvpn_pki_state.newly_revoked_clients(None, after) == []
    assert openvpn_pki_state.server_identity_changed(None, after) is True
