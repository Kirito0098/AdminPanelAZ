"""Blocked peers are re-applied with one runtime call instead of one per client."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AmneziaWg2AccessPolicy, Node, NodeStatus, WgAccessPolicy
from app.services import access_policy, runtime_peer_batch
from app.services.access_policy import AccessPolicyService
from app.services.node_adapter import RemoteNodeAdapter


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
    "wg": (
        WgAccessPolicy,
        "_reapply_all_blocked_runtime",
        "block_wireguard_clients_runtime",
        "block_wireguard_client_runtime",
    ),
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


def test_reapply_without_adapter_uses_local_batch(db, monkeypatch):
    wg_batch = MagicMock(return_value={"temp": {"success": True}, "perm": {"success": True}})
    monkeypatch.setattr(access_policy, "wg_block_clients_runtime", wg_batch)
    reapply, service = _service(db, "wg", None)

    results = reapply()

    wg_batch.assert_called_once_with(["temp", "perm"])
    assert len(results) == 2
    assert service.wg_runtime_calls == 1


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
