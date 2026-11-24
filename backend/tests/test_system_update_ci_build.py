"""Интерфейс из CI (dist/.build-info.json): для того же коммита панель не запускает npm повторно.

Сервер на 1 GB RAM не собирает vite (JavaScript heap out of memory), поэтому обновление из панели
должно довольствоваться готовым dist из релиза, а кнопка «Пересобрать» — собирать принудительно.
"""

import json
import subprocess
from pathlib import Path

from app.services import system_update

OTHER_COMMIT = "0" * 40


def _git_head(repo: Path) -> str:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)

    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
    return run("rev-parse", "HEAD").stdout.strip()


def _repo_with_build(tmp_path: Path, commit: str) -> Path:
    frontend = tmp_path / "frontend"
    (frontend / "dist" / ".vite").mkdir(parents=True)
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (frontend / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    (frontend / "dist" / ".build-info.json").write_text(json.dumps({"commit": commit}), encoding="utf-8")
    return tmp_path


def test_ci_build_skips_npm_ci_and_build(tmp_path: Path, monkeypatch):
    repo = _repo_with_build(tmp_path, _git_head(tmp_path))
    commands: list[list[str]] = []

    def fake_run(args, *, cwd, timeout, label):
        commands.append(args)
        return {"success": True, "output": "", "error": None}

    monkeypatch.setattr(system_update, "_run_command", fake_run)

    assert system_update.install_frontend_requirements(repo)["skipped"] is True
    assert system_update.build_frontend(repo)["skipped"] is True
    assert commands == []


def test_build_for_other_commit_runs_npm(tmp_path: Path, monkeypatch):
    repo = _repo_with_build(tmp_path, OTHER_COMMIT)
    _git_head(tmp_path)
    commands: list[list[str]] = []

    def fake_run(args, *, cwd, timeout, label):
        commands.append(args)
        return {"success": True, "output": "", "error": None}

    monkeypatch.setattr(system_update, "_run_command", fake_run)

    assert system_update.install_frontend_requirements(repo)["skipped"] is False
    assert system_update.build_frontend(repo)["skipped"] is False
    assert commands == [["npm", "ci"], ["npm", "run", "build:all"]]


def test_forced_rebuild_ignores_ci_build(tmp_path: Path, monkeypatch):
    repo = _repo_with_build(tmp_path, _git_head(tmp_path))
    commands: list[list[str]] = []

    def fake_run(args, *, cwd, timeout, label):
        commands.append(args)
        return {"success": True, "output": "", "error": None}

    monkeypatch.setattr(system_update, "_run_command", fake_run)

    assert system_update.build_frontend(repo, force=True)["skipped"] is False
    assert commands == [["npm", "run", "build:all"]]
