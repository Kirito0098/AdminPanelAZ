"""A crash while saving settings must never leave a truncated .env: readers see the old or the new file."""

from __future__ import annotations

import importlib
import os
import shutil
import stat
import subprocess
import tempfile
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
    assert not [p.name for p in env_file.parent.iterdir() if p.name.startswith(".tmp_")]


@pytest.mark.parametrize("writer", WRITERS)
def test_written_env_is_owner_only(env_file: Path, monkeypatch, writer):
    _writers(monkeypatch, env_file)[writer]()
    assert _mode(env_file) == 0o600
    assert "SECRET_KEY=keep-me" in env_file.read_text(encoding="utf-8")
    assert not [p.name for p in env_file.parent.iterdir() if p.name.startswith(".tmp_")]


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


def test_temp_file_is_gitignored(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[2]
    if shutil.which("git") is None or subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-dir"], capture_output=True
    ).returncode:
        pytest.skip("not a git checkout")
    names: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        names.append(Path(name).name)
        return fd, name

    monkeypatch.setattr(atomic_file.tempfile, "mkstemp", mkstemp)
    EnvFileService(tmp_path / ".env").set_env_value("KEY", "v")
    assert names
    ignored = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "-q", "--no-index", f"backend/{names[0]}"]
    )
    assert ignored.returncode == 0, names[0]


def test_symlinked_env_updates_target(tmp_path: Path):
    real = tmp_path / "real.env"
    real.write_text(ORIGINAL, encoding="utf-8")
    link = tmp_path / ".env"
    link.symlink_to(real)
    EnvFileService(link).set_env_value("PANEL_DOMAIN", "new.example")
    assert link.is_symlink()
    assert "PANEL_DOMAIN=new.example" in real.read_text(encoding="utf-8")


def test_directory_sync_failure_does_not_fail_completed_write(env_file: Path, monkeypatch):
    real_fsync = os.fsync

    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("EINVAL")
        real_fsync(fd)

    monkeypatch.setattr(atomic_file.os, "fsync", fsync)
    EnvFileService(env_file).set_env_value("PANEL_DOMAIN", "new.example")
    assert "PANEL_DOMAIN=new.example" in env_file.read_text(encoding="utf-8")


def test_agent_creates_missing_env_file_for_rotated_key(tmp_path: Path, monkeypatch):
    env_file = tmp_path / "node_agent.env"
    _agent_module(monkeypatch, env_file)._persist_api_key("c" * 40)
    assert env_file.read_text(encoding="utf-8") == f"NODE_AGENT_API_KEY={'c' * 40}\n"
    assert _mode(env_file) == 0o600


def test_concurrent_saves_keep_every_key(env_file: Path):
    import threading

    service = EnvFileService(env_file)
    barrier = threading.Barrier(8)

    def save(i: int):
        barrier.wait()
        for round_ in range(15):
            service.set_env_value(f"KEY_{i}", str(round_))

    threads = [threading.Thread(target=save, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    text = env_file.read_text(encoding="utf-8")
    assert all(f"KEY_{i}=14\n" in text for i in range(8)), text
    assert "SECRET_KEY=keep-me" in text
