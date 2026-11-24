"""Обновление из панели сначала ставит готовый интерфейс из GitHub (канал frontend-builds).

Серверный npm остаётся fallback: если сборки для коммита нет (код 3), канал недоступен (4)
или архив не прошёл проверку (1), обновление собирает интерфейс как раньше.
"""

import json
import subprocess
from pathlib import Path

from app.services import system_update

NO_ARTIFACT = 3
CHANNEL_UNAVAILABLE = 4
VERIFY_FAILED = 1


def _repo_with_script(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "panel-frontend-deploy.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (tmp_path / "frontend").mkdir()

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True)

    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
    return tmp_path


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _fake_run(code: int, commands: list[list[str]]):
    def fake_run(args, *, cwd, timeout, label):
        commands.append(args)
        return {"success": code == 0, "returncode": code, "output": "out", "error": None}

    return fake_run


def test_artifact_installs_for_head_without_npm(tmp_path: Path, monkeypatch):
    repo = _repo_with_script(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(system_update, "_run_command", _fake_run(0, commands))
    monkeypatch.setattr(
        system_update, "install_frontend_requirements", lambda _root: (_ for _ in ()).throw(AssertionError("npm"))
    )
    monkeypatch.setattr(system_update, "build_frontend", lambda _root, force=False: (_ for _ in ()).throw(AssertionError("npm")))

    result = system_update.install_frontend_artifact(repo)

    assert result["success"] is True
    assert result["skipped"] is False
    assert commands[0][0] == "bash"
    assert commands[0][2:] == ["--commit", _head(repo), "--dir", str(repo), "--no-restart"]


def test_artifact_reuses_build_for_current_commit(tmp_path: Path, monkeypatch):
    repo = _repo_with_script(tmp_path)
    dist = repo / "frontend" / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / ".build-info.json").write_text(json.dumps({"commit": _head(repo)}), encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(system_update, "_run_command", _fake_run(0, commands))

    assert system_update.install_frontend_artifact(repo)["skipped"] is True
    assert commands == []

    # Переустановка (кнопка «Переустановить интерфейс») не доверяет уже лежащей сборке.
    system_update.install_frontend_artifact(repo, reuse_local=False)
    assert commands[0][0] == "bash"


def test_update_falls_back_to_npm_when_no_artifact(tmp_path: Path, monkeypatch):
    repo = _repo_with_script(tmp_path)
    (repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (repo / "backend" / "data").mkdir(parents=True)
    monkeypatch.setattr(system_update, "git_pull", lambda _root: {"success": True, "output": "ok", "error": None})
    monkeypatch.setattr(
        system_update,
        "install_backend_requirements",
        lambda _root: {"success": True, "skipped": True, "output": "skip", "error": None},
    )
    npm: list[list[str]] = []

    def fake_run(args, *, cwd, timeout, label):
        if args[0] == "bash":
            return {"success": False, "returncode": NO_ARTIFACT, "output": "нет сборки", "error": "нет сборки"}
        npm.append(args)
        return {"success": True, "returncode": 0, "output": "", "error": None}

    monkeypatch.setattr(system_update, "_run_command", fake_run)
    monkeypatch.setattr(system_update, "schedule_controller_restart", lambda _root: None)
    monkeypatch.setattr(system_update, "refresh_installed_systemd_units", lambda *a, **k: {"success": True})

    result = system_update.apply_controller_update(repo_root=repo)

    assert result["success"] is True
    assert npm == [["npm", "ci"], ["npm", "run", "build:all"]]
    assert "нет сборки" in result["output"]


def test_update_skips_npm_when_artifact_installed(tmp_path: Path, monkeypatch):
    repo = _repo_with_script(tmp_path)
    (repo / "backend" / "data").mkdir(parents=True)
    monkeypatch.setattr(system_update, "git_pull", lambda _root: {"success": True, "output": "ok", "error": None})
    monkeypatch.setattr(
        system_update,
        "install_backend_requirements",
        lambda _root: {"success": True, "skipped": True, "output": "skip", "error": None},
    )
    monkeypatch.setattr(system_update, "_run_command", _fake_run(0, []))
    monkeypatch.setattr(
        system_update, "install_frontend_requirements", lambda _root: (_ for _ in ()).throw(AssertionError("npm"))
    )
    monkeypatch.setattr(system_update, "build_frontend", lambda _root, force=False: (_ for _ in ()).throw(AssertionError("npm")))
    monkeypatch.setattr(system_update, "schedule_controller_restart", lambda _root: None)
    monkeypatch.setattr(system_update, "refresh_installed_systemd_units", lambda *a, **k: {"success": True})

    result = system_update.apply_controller_update(repo_root=repo)

    assert result["success"] is True
    assert result["detail"]["frontend_artifact"]["success"] is True


def test_broken_artifact_never_installed_and_falls_back(tmp_path: Path, monkeypatch):
    repo = _repo_with_script(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(system_update, "_run_command", _fake_run(VERIFY_FAILED, commands))

    result = system_update.install_frontend_artifact(repo)

    assert result["success"] is False
    assert result["error"] == f"готовая сборка не прошла проверку (код {VERIFY_FAILED})"


def test_non_github_origin_marks_channel_unavailable(tmp_path: Path, monkeypatch):
    repo = _repo_with_script(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(system_update, "_run_command", _fake_run(CHANNEL_UNAVAILABLE, commands))

    result = system_update.install_frontend_artifact(repo)

    assert result["success"] is False
    assert result["error"] == f"готовой сборки нет (код {CHANNEL_UNAVAILABLE})"
