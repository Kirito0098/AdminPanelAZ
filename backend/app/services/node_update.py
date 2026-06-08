"""Git-based updates for node agent on VPN nodes."""

from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SYSTEMD_UNIT = "adminpanelaz-node"

DEFAULT_GIT_BRANCH = "main"
GIT_TIMEOUT = 120.0


def resolve_repo_root(start: Path | None = None) -> Path | None:
    start = start or Path(__file__).resolve().parents[2]
    for candidate in (start, start.parent):
        if (candidate / ".git").is_dir():
            return candidate
    return None


def _git_run(args: list[str], cwd: Path, *, timeout: float = GIT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def check_git_updates(repo_path: Path, *, branch: str = DEFAULT_GIT_BRANCH) -> dict[str, Any]:
    if not repo_path.is_dir():
        return {"path": str(repo_path), "error": "Каталог не найден", "updates_available": False}
    if not (repo_path / ".git").is_dir():
        return {"path": str(repo_path), "error": "Не git-репозиторий", "updates_available": False}

    try:
        fetch = _git_run(["fetch", "origin"], repo_path, timeout=60.0)
        if fetch.returncode != 0:
            return {
                "path": str(repo_path),
                "error": (fetch.stderr or fetch.stdout or "git fetch failed").strip(),
                "updates_available": False,
            }

        local = _git_run(["rev-parse", "HEAD"], repo_path, timeout=10.0)
        remote = _git_run(["rev-parse", f"origin/{branch}"], repo_path, timeout=10.0)
        local_hash = local.stdout.strip()
        remote_hash = remote.stdout.strip()

        if not local_hash or not remote_hash:
            return {
                "path": str(repo_path),
                "error": "Не удалось определить git hash",
                "updates_available": False,
            }

        behind = 0
        if local_hash != remote_hash:
            count = _git_run(["rev-list", "--count", f"{local_hash}..{remote_hash}"], repo_path, timeout=15.0)
            behind = int(count.stdout.strip() or "0")

        return {
            "path": str(repo_path),
            "local_hash": local_hash[:12],
            "remote_hash": remote_hash[:12],
            "updates_available": behind > 0,
            "commits_behind": behind,
        }
    except subprocess.TimeoutExpired:
        return {"path": str(repo_path), "error": "Таймаут git", "updates_available": False}
    except OSError as exc:
        return {"path": str(repo_path), "error": str(exc), "updates_available": False}


def git_pull(repo_path: Path, *, branch: str = DEFAULT_GIT_BRANCH) -> dict[str, Any]:
    if not repo_path.is_dir() or not (repo_path / ".git").is_dir():
        return {"success": False, "output": "", "error": "Не git-репозиторий"}

    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return {
            "success": result.returncode == 0,
            "output": output.strip(),
            "error": None if result.returncode == 0 else output.strip() or "git pull failed",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Таймаут git pull"}
    except OSError as exc:
        return {"success": False, "output": "", "error": str(exc)}


def _pip_install(repo_root: Path) -> dict[str, Any]:
    venv_pip = repo_root / "backend" / ".venv" / "bin" / "pip"
    req = repo_root / "backend" / "requirements.txt"
    if not venv_pip.is_file() or not req.is_file():
        return {"skipped": True, "output": ""}
    try:
        result = subprocess.run(
            [str(venv_pip), "install", "-q", "-r", str(req)],
            capture_output=True,
            text=True,
            timeout=300.0,
            check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return {"skipped": False, "success": result.returncode == 0, "output": output.strip()}
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"skipped": False, "success": False, "output": str(exc)}


def _restart_log_path(repo_root: Path) -> Path:
    state = os.environ.get("NODE_AGENT_STATE_DIR")
    if state:
        return Path(state) / "logs" / "update-restart.log"
    return repo_root / ".runtime" / "node" / "logs" / "update-restart.log"


def _append_restart_log(log_path: Path, message: str) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")
    except OSError:
        pass


def _systemd_unit_installed(unit: str = SYSTEMD_UNIT) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "cat", unit],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def restart_node_agent(repo_root: Path) -> dict[str, Any]:
    """Restart node agent after git pull. Prefer systemd when the unit is installed."""
    log_path = _restart_log_path(repo_root)
    script = repo_root / "start_node_agent.sh"

    if _systemd_unit_installed():
        try:
            result = subprocess.run(
                ["systemctl", "restart", SYSTEMD_UNIT],
                capture_output=True,
                text=True,
                timeout=180.0,
                check=False,
            )
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            success = result.returncode == 0
            _append_restart_log(
                log_path,
                f"systemctl restart {SYSTEMD_UNIT}: rc={result.returncode}"
                + (f" — {output}" if output else ""),
            )
            return {
                "method": "systemd",
                "success": success,
                "output": output,
                "error": None if success else output or f"systemctl restart {SYSTEMD_UNIT} failed",
            }
        except (subprocess.TimeoutExpired, OSError) as exc:
            _append_restart_log(log_path, f"systemctl restart {SYSTEMD_UNIT}: {exc}")
            return {"method": "systemd", "success": False, "output": "", "error": str(exc)}

    if not script.is_file():
        message = f"Не найден {script} и unit {SYSTEMD_UNIT}"
        _append_restart_log(log_path, message)
        return {"method": "none", "success": False, "output": "", "error": message}

    try:
        result = subprocess.run(
            [str(script), "restart"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=180.0,
            check=False,
        )
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        success = result.returncode == 0
        _append_restart_log(
            log_path,
            f"{script} restart: rc={result.returncode}" + (f" — {output}" if output else ""),
        )
        return {
            "method": "script",
            "success": success,
            "output": output,
            "error": None if success else output or "start_node_agent.sh restart failed",
        }
    except (subprocess.TimeoutExpired, OSError) as exc:
        _append_restart_log(log_path, f"{script} restart: {exc}")
        return {"method": "script", "success": False, "output": "", "error": str(exc)}


def schedule_agent_restart(repo_root: Path, *, delay_seconds: float = 1.5) -> None:
    def _restart() -> None:
        restart_node_agent(repo_root)

    timer = threading.Timer(delay_seconds, _restart)
    timer.daemon = True
    timer.start()


def check_agent_updates(*, repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root or resolve_repo_root()
    return {
        "agent": check_git_updates(repo_root) if repo_root else {"error": "Репозиторий панели не найден", "updates_available": False},
    }


def apply_node_update(
    *,
    agent_version: str = "1.0.0",
    repo_root: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root or resolve_repo_root()

    before = {"agent_version": agent_version}
    detail: dict[str, Any] = {}
    messages: list[str] = []
    errors: list[str] = []
    restarting = False

    if not repo_root:
        errors.append("Репозиторий панели (node agent) не найден")
    else:
        pull = git_pull(repo_root)
        detail["agent_pull"] = pull
        if pull["success"]:
            detail["pip"] = _pip_install(repo_root)
            messages.append("Node agent обновлён, перезапуск через несколько секунд")
            schedule_agent_restart(repo_root)
            restarting = True
        else:
            errors.append(pull.get("error") or "Ошибка git pull node agent")

    after_agent_version = before["agent_version"]
    if not errors and detail.get("agent_pull", {}).get("success"):
        after_agent_version = agent_version

    success = not errors
    message = "; ".join(messages) if messages else ("Обновление не выполнено" if errors else "Нечего обновлять")

    return {
        "success": success,
        "message": message,
        "errors": errors,
        "restarting": restarting,
        "before": before,
        "after": {"agent_version": after_agent_version},
        "detail": detail,
    }
