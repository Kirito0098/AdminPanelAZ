"""Update from the panel installs frontend deps strictly from package-lock.json, like install.sh and the menu."""

from pathlib import Path
from unittest.mock import MagicMock

from app.services import system_update


def test_install_frontend_requirements_runs_npm_ci(tmp_path: Path, monkeypatch):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    calls: list[dict] = []

    def fake_run(args, *, cwd, timeout, label):
        calls.append({"args": args, "cwd": cwd, "label": label})
        return {"success": False, "output": "", "error": f"{label} failed (exit 1)"}

    monkeypatch.setattr(system_update, "_run_command", fake_run)

    result = system_update.install_frontend_requirements(tmp_path)

    assert calls == [{"args": ["npm", "ci"], "cwd": tmp_path / "frontend", "label": "npm ci"}]
    assert result["success"] is False
    assert result["skipped"] is False


def test_apply_controller_update_reports_npm_ci_failure(tmp_path: Path, monkeypatch):
    (tmp_path / "backend" / "data").mkdir(parents=True)
    (tmp_path / "frontend").mkdir(parents=True)
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(system_update, "git_pull", lambda _root: {"success": True, "output": "ok", "error": None})
    monkeypatch.setattr(
        system_update,
        "install_backend_requirements",
        lambda _root: {"success": True, "skipped": True, "output": "skip", "error": None},
    )
    commands: list[list[str]] = []

    def fake_run(args, *, cwd, timeout, label):
        commands.append(args)
        return {"success": False, "output": "npm ERR! lock out of sync", "error": None}

    monkeypatch.setattr(system_update, "_run_command", fake_run)
    build = MagicMock()
    monkeypatch.setattr(system_update, "build_frontend", build)
    restart = MagicMock()
    monkeypatch.setattr(system_update, "schedule_controller_restart", restart)
    stages: list[str] = []

    result = system_update.apply_controller_update(
        repo_root=tmp_path, progress=lambda _percent, stage: stages.append(stage)
    )

    assert commands == [["npm", "ci"]]
    assert result["success"] is False
    assert result["restarting"] is False
    assert result["errors"] == ["Ошибка: npm ci"]
    assert "[npm ci]\nnpm ERR! lock out of sync" in result["output"]
    assert "Обновление: npm ci…" in stages
    build.assert_not_called()
    restart.assert_not_called()
