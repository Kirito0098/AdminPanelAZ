"""Git-based updates for node agent and AntiZapret on VPN nodes."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.antizapret import AntiZapretService

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


def schedule_agent_restart(repo_root: Path, *, delay_seconds: float = 1.5) -> None:
    script = repo_root / "start_node_agent.sh"
    if not script.is_file():
        return

    def _restart() -> None:
        subprocess.run(
            [str(script), "restart"],
            cwd=repo_root,
            capture_output=True,
            timeout=180.0,
            check=False,
        )

    timer = threading.Timer(delay_seconds, _restart)
    timer.daemon = True
    timer.start()


def check_all_updates(*, antizapret_path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root or resolve_repo_root()
    return {
        "agent": check_git_updates(repo_root) if repo_root else {"error": "Репозиторий панели не найден", "updates_available": False},
        "antizapret": check_git_updates(antizapret_path),
    }


def apply_node_update(
    *,
    antizapret_path: Path,
    service: AntiZapretService,
    scope: str = "all",
    run_doall: bool = True,
    agent_version: str = "1.0.0",
    repo_root: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root or resolve_repo_root()
    scope = scope if scope in ("all", "agent", "antizapret") else "all"

    before = {
        "agent_version": agent_version,
        "antizapret_version": service.get_antizapret_version(),
    }
    detail: dict[str, Any] = {"scope": scope}
    messages: list[str] = []
    errors: list[str] = []
    restarting = False

    if scope in ("all", "antizapret"):
        pull = git_pull(antizapret_path)
        detail["antizapret_pull"] = pull
        if pull["success"]:
            messages.append("AntiZapret обновлён")
            if run_doall:
                try:
                    doall_output = service.apply_config_changes()
                    detail["doall_output"] = doall_output
                    messages.append("doall.sh выполнен")
                except Exception as exc:
                    errors.append(f"doall.sh: {exc}")
        else:
            errors.append(pull.get("error") or "Ошибка git pull AntiZapret")

    if scope in ("all", "agent"):
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
    if scope in ("all", "agent") and not errors and detail.get("agent_pull", {}).get("success"):
        after_agent_version = agent_version  # new version visible after agent restart + health poll

    after_antizapret_version = before["antizapret_version"]
    if scope in ("all", "antizapret") and not errors:
        after_antizapret_version = service.get_antizapret_version()

    success = not errors
    message = "; ".join(messages) if messages else ("Обновление не выполнено" if errors else "Нечего обновлять")

    return {
        "success": success,
        "message": message,
        "errors": errors,
        "restarting": restarting,
        "before": before,
        "after": {
            "agent_version": after_agent_version,
            "antizapret_version": after_antizapret_version,
        },
        "detail": detail,
    }
