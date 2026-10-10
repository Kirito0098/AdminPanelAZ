"""Long node agent operations (PKI, backup restore, profile and AWG2 imports) run off the event loop."""

from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from app.services.awg2 import Awg2NotInstalledError


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)
    import node_agent.main as agent_main

    return agent_main, TestClient(agent_main.app), {"X-Node-Key": agent_main.NODE_AGENT_API_KEY}


ARCHIVE = {"archive": ("archive.tar.gz", b"archive-bytes", "application/gzip")}


@pytest.mark.parametrize(
    "path, method",
    [
        ("/openvpn/easyrsa3/import", "import_easyrsa3_archive"),
        ("/backups/antizapret/restore", "restore_antizapret_backup"),
        ("/backups/antizapret/restore?ha_replica=true", "restore_antizapret_backup_for_ha_replica"),
        ("/profiles/wireguard/import", "import_wireguard_client_profiles_archive"),
        ("/profiles/openvpn/import", "import_openvpn_client_profiles_archive"),
    ],
)
def test_archive_operations_run_off_the_event_loop(agent, monkeypatch, path, method):
    agent_main, client, headers = agent
    seen: list[bool] = []

    def fake(*_args):
        seen.append(_on_event_loop())
        return {}

    monkeypatch.setattr(agent_main.service, method, fake)

    response = client.post(path, files=ARCHIVE, headers=headers)

    assert response.status_code == 200
    assert seen == [False]


class _FakeAwg2:
    calls: list[tuple] = []
    error: Exception | None = None

    def import_narrow_backup(self, data):
        if self.error:
            raise self.error
        self.calls.append(("import_narrow_backup", data, _on_event_loop()))

    def apply_runtime(self):
        self.calls.append(("apply_runtime", _on_event_loop()))
        return {"success": True}

    def import_state_archive(self, data):
        self.calls.append(("import_state_archive", data, _on_event_loop()))


@pytest.fixture
def fake_awg2(agent, monkeypatch):
    agent_main, _client, _headers = agent
    _FakeAwg2.calls = []
    _FakeAwg2.error = None
    monkeypatch.setattr(agent_main, "Awg2Service", _FakeAwg2)
    return _FakeAwg2


def test_awg2_restore_runs_off_the_event_loop(agent, fake_awg2):
    _agent_main, client, headers = agent

    response = client.post("/awg2/restore", files=ARCHIVE, headers=headers)

    assert response.json() == {"success": True}
    assert fake_awg2.calls == [("import_narrow_backup", b"archive-bytes", False), ("apply_runtime", False)]


def test_awg2_restore_still_maps_not_installed_to_409(agent, fake_awg2):
    _agent_main, client, headers = agent
    fake_awg2.error = Awg2NotInstalledError("AZ-AWG2 не установлен")

    response = client.post("/awg2/restore", files=ARCHIVE, headers=headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "AZ-AWG2 не установлен"}


def test_awg2_state_import_runs_off_the_event_loop(agent, fake_awg2):
    _agent_main, client, headers = agent

    response = client.post("/awg2/state/archive", content=b"state-bytes", headers=headers)

    assert response.json() == {"success": True}
    assert fake_awg2.calls == [("import_state_archive", b"state-bytes", False)]
