"""Blocked peers are re-applied with one runtime call instead of one per client."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AmneziaWg2AccessPolicy, Node, NodeStatus, WgAccessPolicy
from app.services import access_policy, awg2_runtime, runtime_peer_batch, wg_runtime
from app.services.access_policy import AccessPolicyService
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter


class _Runner:
    def __init__(self, fail=lambda args: False):
        self.calls: list[list[str]] = []
        self._fail = fail

    def __call__(self, args, timeout=None):
        self.calls.append(list(args))
        failed = self._fail(args)
        return subprocess.CompletedProcess(args, 1 if failed else 0, "", "boom" if failed else "")


def _peer_keys(args: list[str]) -> list[str]:
    return [args[i + 1] for i, arg in enumerate(args) if arg == "peer"]


def test_block_peers_batch_uses_one_command_per_interface():
    run = _Runner()
    results = runtime_peer_batch.block_peers_batch(
        {"alice": [("vpn", "A1"), ("antizapret", "A2")], "bob": [("vpn", "B1")], "ghost": []},
        tool="wg",
        run=run,
    )

    assert sorted((args[2], _peer_keys(args)) for args in run.calls) == [("antizapret", ["A2"]), ("vpn", ["A1", "B1"])]
    assert all(args[:2] == ["wg", "set"] and args.count("remove") == len(_peer_keys(args)) for args in run.calls)
    assert results["alice"]["success"] is True and results["alice"]["removed_count"] == 2
    assert results["bob"] == {"success": True, "removed_count": 1, "blocked": 1, "error_count": 0, "errors": []}
    assert results["ghost"]["success"] is False
    assert results["ghost"]["errors"] == [{"interface": None, "stderr": runtime_peer_batch.NO_PEERS_ERROR}]


def test_block_peers_batch_attributes_failures_per_peer():
    run = _Runner(fail=lambda args: "B1" in args)
    results = runtime_peer_batch.block_peers_batch(
        {"alice": [("vpn", "A1")], "bob": [("vpn", "B1"), ("antizapret", "B2")]},
        tool="awg",
        run=run,
    )

    assert results["alice"]["success"] is True
    assert results["bob"]["removed_count"] == 1
    assert results["bob"]["errors"] == [{"interface": "vpn", "peer_public_key": "B1", "stderr": "boom"}]
    assert ["awg", "set", "vpn", "peer", "A1", "remove"] in run.calls


def test_block_peers_batch_reports_client_with_no_removed_peers():
    run = _Runner(fail=lambda args: "B1" in args)
    results = runtime_peer_batch.block_peers_batch({"bob": [("vpn", "B1")]}, tool="wg", run=run)

    assert results["bob"]["success"] is False
    assert results["bob"]["removed_count"] == 0


def test_block_peers_batch_splits_large_batches(monkeypatch):
    monkeypatch.setattr(runtime_peer_batch, "PEERS_PER_COMMAND", 2)
    run = _Runner()
    runtime_peer_batch.block_peers_batch(
        {f"c{i}": [("vpn", f"K{i}")] for i in range(5)} | {"dup": [("vpn", "K0")]},
        tool="wg",
        run=run,
    )

    assert [_peer_keys(args) for args in run.calls] == [["K0", "K1"], ["K2", "K3"], ["K4"]]


def _wg_conf(*peers: tuple[str, str]) -> str:
    body = "[Interface]\nPrivateKey = x\n"
    for client, key in peers:
        body += f"\n# Client = {client}\n[Peer]\nPublicKey = {key}\nAllowedIPs = 10.0.0.2/32\n"
    return body


def test_wg_block_clients_runtime_reads_configs_once(tmp_path, monkeypatch):
    files = {"antizapret": tmp_path / "antizapret.conf", "vpn": tmp_path / "vpn.conf"}
    files["antizapret"].write_text(_wg_conf(("Alice", "A1"), ("bob", "B1"), ("carol", "C1")))
    files["vpn"].write_text(_wg_conf(("alice", "A2"), ("bob", "B2")))
    monkeypatch.setattr(wg_runtime, "WG_CONFIG_FILES", files)
    run = _Runner()
    monkeypatch.setattr(wg_runtime, "_run", run)

    results = wg_runtime.block_clients_runtime(["alice", "BOB", "ghost"])

    assert sorted((args[2], _peer_keys(args)) for args in run.calls) == [
        ("antizapret", ["A1", "B1"]),
        ("vpn", ["A2", "B2"]),
    ]
    assert {name: result["removed_count"] for name, result in results.items()} == {"alice": 2, "bob": 2, "ghost": 0}


def test_awg2_block_clients_runtime_uses_awg(tmp_path, monkeypatch):
    conf = tmp_path / "vpn-awg.conf"
    conf.write_text(_wg_conf(("alice", "A1"), ("bob", "B1")))
    run = _Runner()
    monkeypatch.setattr(awg2_runtime, "_run", run)

    results = awg2_runtime.block_clients_runtime(["bob"], config_files={"vpn-awg": conf})

    assert run.calls == [["awg", "set", "vpn-awg", "peer", "B1", "remove"]]
    assert results["bob"]["removed_count"] == 1


@pytest.fixture
def db(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.info["antizapret_path"] = tmp_path
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _node(db) -> Node:
    node = Node(
        name="replica",
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=False,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    return node


def _blocked_rows(model, node_id: int) -> list:
    return [
        model(
            node_id=node_id,
            client_name="temp",
            is_temp_blocked=True,
            block_reason="manual_temp",
            block_started_at=datetime.utcnow(),
            block_days=2,
            block_until=datetime.utcnow() + timedelta(days=2),
        ),
        model(node_id=node_id, client_name="open"),
        model(
            node_id=node_id,
            client_name="perm",
            is_permanent_blocked=True,
            block_reason="manual_permanent",
            block_started_at=datetime.utcnow(),
        ),
    ]


_PROTOCOLS = {
    "wg": (WgAccessPolicy, "_reapply_all_blocked_runtime", "block_wireguard_clients_runtime", "block_wireguard_client_runtime"),
    "awg2": (
        AmneziaWg2AccessPolicy,
        "_reapply_all_blocked_awg2_runtime",
        "block_awg2_clients_runtime",
        "block_awg2_client_runtime",
    ),
}


def _service(db, protocol: str, adapter):
    model, reapply, _, _ = _PROTOCOLS[protocol]
    node = _node(db)
    db.add_all(_blocked_rows(model, node.id))
    db.commit()
    service = AccessPolicyService(
        db,
        antizapret_path=db.info["antizapret_path"],
        node_id=node.id,
        node_name=node.name,
        adapter=adapter,
    )
    return getattr(service, reapply), service


@pytest.mark.parametrize("protocol", ["wg", "awg2"])
def test_reapply_blocks_all_clients_in_one_call(db, protocol):
    _, _, batch_name, single_name = _PROTOCOLS[protocol]
    adapter = MagicMock()
    getattr(adapter, batch_name).return_value = {"temp": {"success": True}, "perm": {"success": False}}
    reapply, _ = _service(db, protocol, adapter)

    results = reapply()

    getattr(adapter, batch_name).assert_called_once_with(["temp", "perm"])
    getattr(adapter, single_name).assert_not_called()
    assert results == [
        {"client_name": "temp", "result": {"success": True}},
        {"client_name": "perm", "result": {"success": False}},
    ]


@pytest.mark.parametrize("protocol", ["wg", "awg2"])
def test_reapply_matches_results_to_mixed_case_rows(db, protocol):
    model, _, batch_name, _ = _PROTOCOLS[protocol]
    adapter = MagicMock()
    getattr(adapter, batch_name).return_value = {"temp": {"success": True}, "perm": {"success": True}}
    reapply, _ = _service(db, protocol, adapter)
    db.query(model).filter_by(client_name="temp").update({"client_name": "Temp"})
    db.commit()

    results = reapply()

    getattr(adapter, batch_name).assert_called_once_with(["temp", "perm"])
    assert results[0] == {"client_name": "Temp", "result": {"success": True}}


@pytest.mark.parametrize("protocol", ["wg", "awg2"])
def test_reapply_skips_the_call_when_nothing_is_blocked(db, protocol):
    _, _, batch_name, _ = _PROTOCOLS[protocol]
    adapter = MagicMock()
    reapply, _ = _service(db, protocol, adapter)

    assert reapply(exclude_client="temp") != []
    getattr(adapter, batch_name).reset_mock()
    db.query(_PROTOCOLS[protocol][0]).delete()
    db.commit()

    assert reapply() == []
    getattr(adapter, batch_name).assert_not_called()


@pytest.mark.parametrize("protocol", ["wg", "awg2"])
@pytest.mark.parametrize("status_code", [404, 405])
def test_reapply_falls_back_per_client_for_old_agents(db, protocol, status_code):
    _, _, batch_name, single_name = _PROTOCOLS[protocol]
    adapter = MagicMock()
    getattr(adapter, batch_name).side_effect = HTTPException(status_code=status_code, detail="Not Found")
    getattr(adapter, single_name).side_effect = lambda name: {"blocked": name}
    reapply, _ = _service(db, protocol, adapter)

    results = reapply()

    assert getattr(adapter, single_name).call_args_list == [call("temp"), call("perm")]
    assert results == [
        {"client_name": "temp", "result": {"blocked": "temp"}},
        {"client_name": "perm", "result": {"blocked": "perm"}},
    ]


@pytest.mark.parametrize("protocol", ["wg", "awg2"])
@pytest.mark.parametrize(
    "error",
    [HTTPException(status_code=504, detail="timeout"), RuntimeError("agent down")],
    ids=["http-504", "runtime-error"],
)
def test_failed_batch_reports_every_client_without_per_client_retries(db, protocol, error):
    _, _, batch_name, single_name = _PROTOCOLS[protocol]
    adapter = MagicMock()
    getattr(adapter, batch_name).side_effect = error
    reapply, _ = _service(db, protocol, adapter)

    results = reapply()

    getattr(adapter, single_name).assert_not_called()
    assert [item["client_name"] for item in results] == ["temp", "perm"]
    assert all(item["error"] for item in results)


@pytest.mark.parametrize("protocol", ["wg", "awg2"])
def test_adapter_without_batch_method_is_called_per_client(db, protocol):
    _, _, batch_name, single_name = _PROTOCOLS[protocol]
    adapter = SimpleNamespace(**{single_name: MagicMock(return_value={"ok": True})})
    reapply, _ = _service(db, protocol, adapter)

    results = reapply()

    assert getattr(adapter, single_name).call_args_list == [call("temp"), call("perm")]
    assert [item["result"] for item in results] == [{"ok": True}, {"ok": True}]


def test_reapply_without_adapter_uses_local_batch(db, monkeypatch):
    wg_batch = MagicMock(return_value={"temp": {"success": True}, "perm": {"success": True}})
    monkeypatch.setattr(access_policy, "wg_block_clients_runtime", wg_batch)
    reapply, service = _service(db, "wg", None)

    results = reapply()

    wg_batch.assert_called_once_with(["temp", "perm"])
    assert len(results) == 2
    assert service.wg_runtime_calls == 1


def test_reapply_without_adapter_uses_local_awg2_batch(db, monkeypatch):
    awg2_batch = MagicMock(return_value={})
    monkeypatch.setattr(access_policy, "awg2_block_clients_runtime", awg2_batch)
    reapply, _ = _service(db, "awg2", None)

    results = reapply()

    awg2_batch.assert_called_once_with(["temp", "perm"])
    assert results == [{"client_name": "temp", "result": None}, {"client_name": "perm", "result": None}]


def test_remote_adapter_posts_batch_and_unwraps_results():
    adapter = RemoteNodeAdapter(host="127.0.0.1", port=9100, api_key="k" * 32)
    adapter._request = MagicMock(return_value={"results": {"temp": {"success": True}}})

    assert adapter.block_wireguard_clients_runtime(["temp"]) == {"temp": {"success": True}}
    assert adapter.block_awg2_clients_runtime(["temp"]) == {"temp": {"success": True}}

    paths = [(c.args[0], c.args[1], c.kwargs["json"]) for c in adapter._request.call_args_list]
    assert paths == [
        ("POST", "/clients/wireguard/runtime/block-batch", {"client_names": ["temp"]}),
        ("POST", "/clients/amneziawg2/runtime/block-batch", {"client_names": ["temp"]}),
    ]


@pytest.mark.parametrize("method", ["block_wireguard_clients_runtime", "block_awg2_clients_runtime"])
def test_remote_adapter_splits_batches_to_the_agent_limit(method):
    from app.services.runtime_peer_batch import CLIENTS_PER_REQUEST

    names = [f"c{i}" for i in range(CLIENTS_PER_REQUEST * 2 + 1)]
    adapter = RemoteNodeAdapter(host="127.0.0.1", port=9100, api_key="k" * 32)
    adapter._request = MagicMock(
        side_effect=lambda *_a, json, **_k: {"results": {name: {"success": True} for name in json["client_names"]}}
    )

    results = getattr(adapter, method)(names)

    sent = [c.kwargs["json"]["client_names"] for c in adapter._request.call_args_list]
    assert [len(chunk) for chunk in sent] == [CLIENTS_PER_REQUEST, CLIENTS_PER_REQUEST, 1]
    assert [name for chunk in sent for name in chunk] == names
    assert results == {name: {"success": True} for name in names}


def test_agent_batch_limit_matches_the_panel_chunk():
    import node_agent.main as agent_main
    from app.services.runtime_peer_batch import CLIENTS_PER_REQUEST

    # Deployed agents reject more than 5000 names; a bigger panel chunk would 422 on them.
    assert CLIENTS_PER_REQUEST <= 5000
    agent_main.ClientNamesRequest(client_names=["a"] * CLIENTS_PER_REQUEST)
    with pytest.raises(ValueError):
        agent_main.ClientNamesRequest(client_names=["a"] * (CLIENTS_PER_REQUEST + 1))


def test_local_adapter_uses_runtime_batches(monkeypatch):
    import app.services.node_adapter as node_adapter

    monkeypatch.setattr(node_adapter, "wg_block_clients_runtime", lambda names: {"wg": names})
    monkeypatch.setattr(node_adapter, "awg2_block_clients_runtime", lambda names: {"awg2": names})
    adapter = LocalNodeAdapter(service=MagicMock())

    assert adapter.block_wireguard_clients_runtime(["a"]) == {"wg": ["a"]}
    assert adapter.block_awg2_clients_runtime(["a"]) == {"awg2": ["a"]}


@pytest.fixture
def agent_client(monkeypatch):
    import os

    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)
    from fastapi.testclient import TestClient

    import node_agent.main as agent_main

    return agent_main, TestClient(agent_main.app), {"X-Node-Key": agent_main.NODE_AGENT_API_KEY}


@pytest.mark.parametrize(
    "path, target",
    [
        ("/clients/wireguard/runtime/block-batch", "wg_block_clients_runtime"),
        ("/clients/amneziawg2/runtime/block-batch", "awg2_block_clients_runtime"),
    ],
)
def test_agent_batch_endpoints(agent_client, monkeypatch, path, target):
    agent_main, client, headers = agent_client
    batch = MagicMock(return_value={"temp": {"success": True}})
    monkeypatch.setattr(agent_main, target, batch)

    ok = client.post(path, json={"client_names": ["temp", "perm"]}, headers=headers)
    too_long = client.post(path, json={"client_names": ["x" * 33]}, headers=headers)
    unauthorized = client.post(path, json={"client_names": ["temp"]}, headers={"X-Node-Key": "wrong" * 8})

    assert ok.status_code == 200
    assert ok.json() == {"results": {"temp": {"success": True}}}
    batch.assert_called_once_with(["temp", "perm"])
    assert too_long.status_code == 422
    assert unauthorized.status_code == 401
