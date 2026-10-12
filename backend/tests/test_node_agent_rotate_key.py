"""Node agent key rotation: the new key is on disk before the agent starts using it."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

OLD_KEY = "a" * 40
NEW_KEY = "b" * 40


@pytest.fixture
def agent_main(monkeypatch, tmp_path):
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)
    import node_agent.main as agent_main

    monkeypatch.setattr(agent_main, "NODE_AGENT_ENV_FILE", tmp_path / "node_agent.env")
    monkeypatch.setattr(agent_main, "NODE_AGENT_API_KEY", OLD_KEY)
    return agent_main


def _rotate(agent_main):
    client = TestClient(agent_main.app, raise_server_exceptions=False)
    return client.post("/system/rotate-api-key", json={"new_api_key": NEW_KEY}, headers={"X-Node-Key": OLD_KEY})


def test_new_key_is_written_before_it_is_used(agent_main, monkeypatch):
    real_write = agent_main.atomic_write_text
    key_during_write: list[str] = []

    def spy(*args, **kwargs):
        key_during_write.append(agent_main.NODE_AGENT_API_KEY)
        real_write(*args, **kwargs)

    monkeypatch.setattr(agent_main, "atomic_write_text", spy)

    response = _rotate(agent_main)

    assert response.status_code == 200
    assert key_during_write == [OLD_KEY]
    assert agent_main.NODE_AGENT_API_KEY == NEW_KEY
    assert agent_main.NODE_AGENT_ENV_FILE.read_text(encoding="utf-8") == f"NODE_AGENT_API_KEY={NEW_KEY}\n"


def test_failed_key_write_keeps_old_key(agent_main, monkeypatch):
    def disk_full(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(agent_main, "atomic_write_text", disk_full)

    response = _rotate(agent_main)

    assert agent_main.NODE_AGENT_API_KEY == OLD_KEY
    assert response.status_code == 500
    assert "Ключ не изменён" in response.json()["detail"]
