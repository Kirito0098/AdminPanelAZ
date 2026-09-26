"""A crash while saving settings must never leave a truncated .env: readers see the old or the new file."""

from __future__ import annotations

import importlib
import os
import stat
from pathlib import Path

import pytest

from app.services import atomic_file
from app.services.env_file import EnvFileService
from app.services.node_agent_provision import _write_env_updates

ORIGINAL = "SECRET_KEY=keep-me\nPANEL_DOMAIN=old.example\n"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture()
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text(ORIGINAL, encoding="utf-8")
    path.chmod(0o644)
    return path


@pytest.fixture()
def failing_replace(monkeypatch):
    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(atomic_file.os, "replace", boom)


def _agent_module(monkeypatch, env_file: Path):
    monkeypatch.setenv("NODE_AGENT_API_KEY", "a" * 40)
    agent = importlib.import_module("node_agent.main")
    monkeypatch.setattr(agent, "NODE_AGENT_ENV_FILE", env_file)
    monkeypatch.setattr(agent, "NODE_AGENT_API_KEY", agent.NODE_AGENT_API_KEY)
    return agent


def _writers(monkeypatch, env_file: Path):
    service = EnvFileService(env_file)
    return {
        "set_env_value": lambda: service.set_env_value("PANEL_DOMAIN", "new.example"),
        "remove_env_key": lambda: service.remove_env_key("PANEL_DOMAIN"),
        "provision_updates": lambda: _write_env_updates(env_file, {"PANEL_DOMAIN": "new.example"}),
        "agent_persist_key": lambda: _agent_module(monkeypatch, env_file)._persist_api_key("b" * 40),
    }


WRITERS = ["set_env_value", "remove_env_key", "provision_updates", "agent_persist_key"]


@pytest.mark.parametrize("writer", WRITERS)
def test_failed_write_keeps_previous_env(env_file: Path, monkeypatch, failing_replace, writer):
    write = _writers(monkeypatch, env_file)[writer]
    with pytest.raises(OSError):
        write()
    assert env_file.read_text(encoding="utf-8") == ORIGINAL
    assert sorted(p.name for p in env_file.parent.iterdir()) == [".env"]


@pytest.mark.parametrize("writer", WRITERS)
def test_written_env_is_owner_only(env_file: Path, monkeypatch, writer):
    _writers(monkeypatch, env_file)[writer]()
    assert _mode(env_file) == 0o600
    assert "SECRET_KEY=keep-me" in env_file.read_text(encoding="utf-8")
    assert sorted(p.name for p in env_file.parent.iterdir()) == [".env"]


def test_set_env_value_creates_missing_env_owner_only(tmp_path: Path):
    target = tmp_path / "sub" / ".env"
    previous = os.umask(0o022)
    try:
        EnvFileService(target).set_env_value("KEY", "v")
    finally:
        os.umask(previous)
    assert target.read_text(encoding="utf-8") == "KEY=v\n"
    assert _mode(target) == 0o600


def test_data_and_directory_are_synced_before_and_after_replace(env_file: Path, monkeypatch):
    events: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        events.append("fsync-dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "fsync-file")
        real_fsync(fd)

    def replace(src, dst):
        events.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(atomic_file.os, "fsync", fsync)
    monkeypatch.setattr(atomic_file.os, "replace", replace)
    EnvFileService(env_file).set_env_value("PANEL_DOMAIN", "new.example")
    assert events == ["fsync-file", "replace", "fsync-dir"]


def test_symlinked_env_updates_target(tmp_path: Path):
    real = tmp_path / "real.env"
    real.write_text(ORIGINAL, encoding="utf-8")
    link = tmp_path / ".env"
    link.symlink_to(real)
    EnvFileService(link).set_env_value("PANEL_DOMAIN", "new.example")
    assert link.is_symlink()
    assert "PANEL_DOMAIN=new.example" in real.read_text(encoding="utf-8")
