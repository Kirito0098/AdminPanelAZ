"""Git-based updates for node agent on VPN nodes."""

from __future__ import annotations

import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SYSTEMD_UNIT = "adminpanelaz-node"

DEFAULT_GIT_BRANCH = "main"
GIT_TIMEOUT = 120.0
_OID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


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


def resolve_update_ref(repo_path: Path) -> tuple[str | None, str | None]:
    """Remote-tracking ref the checked-out branch updates from, or why there is none.

    The upstream of the current branch; ``origin/main`` for ``main`` without one. A release branch
    must never be moved to another branch's history.
    """
    head = _git_run(["symbolic-ref", "--quiet", "--short", "HEAD"], repo_path, timeout=10.0)
    branch = head.stdout.strip() if head.returncode == 0 else ""
    if not branch:
        return None, "Рабочая копия не на ветке (detached HEAD): обновите вручную"
    upstream = _git_run(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        repo_path,
        timeout=10.0,
    )
    ref = upstream.stdout.strip() if upstream.returncode == 0 else ""
    if ref:
        return ref, None
    if branch == DEFAULT_GIT_BRANCH:
        return f"origin/{DEFAULT_GIT_BRANCH}", None
    return None, (
        f"У ветки {branch} нет upstream: обновите вручную "
        f"или привяжите её (git branch -u origin/{branch})"
    )


def check_git_updates(repo_path: Path) -> dict[str, Any]:
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

        ref, ref_error = resolve_update_ref(repo_path)
        if ref is None:
            return {"path": str(repo_path), "error": ref_error, "updates_available": False}
        local = _git_run(["rev-parse", "HEAD"], repo_path, timeout=10.0)
        remote = _git_run(["rev-parse", ref], repo_path, timeout=10.0)
        local_hash = local.stdout.strip()
        remote_hash = remote.stdout.strip()

        if not local_hash or not remote_hash:
            return {
                "path": str(repo_path),
                "error": "Не удалось определить git hash",
                "updates_available": False,
            }

        behind = 0
        ahead = 0
        if local_hash != remote_hash:
            behind_count = _git_run(
                ["rev-list", "--count", f"{local_hash}..{remote_hash}"],
                repo_path,
                timeout=15.0,
            )
            ahead_count = _git_run(
                ["rev-list", "--count", f"{remote_hash}..{local_hash}"],
                repo_path,
                timeout=15.0,
            )
            behind = int(behind_count.stdout.strip() or "0")
            ahead = int(ahead_count.stdout.strip() or "0")

        diverged = ahead > 0 and behind > 0

        return {
            "path": str(repo_path),
            "local_hash": local_hash[:12],
            "remote_hash": remote_hash[:12],
            "updates_available": behind > 0 or diverged,
            "commits_behind": behind,
            "commits_ahead": ahead,
            "diverged": diverged,
        }
    except subprocess.TimeoutExpired:
        return {"path": str(repo_path), "error": "Таймаут git", "updates_available": False}
    except OSError as exc:
        return {"path": str(repo_path), "error": str(exc), "updates_available": False}


def _working_tree_clean(repo_path: Path) -> bool:
    status = _git_run(["status", "--porcelain"], repo_path, timeout=15.0)
    return status.returncode == 0 and not status.stdout.strip()


def _seen_upstream_tips(repo_path: Path, ref: str) -> list[str]:
    """Every tip of ``refs/remotes/<ref>`` recorded in its reflog, old values included.

    A fresh clone has no reflog for the ref; the first fetch after a force-push records the
    pre-rewrite tip only as the old value of its entry.
    """
    log_path = _git_run(["rev-parse", "--git-path", f"logs/refs/remotes/{ref}"], repo_path, timeout=10.0)
    if log_path.returncode != 0 or not log_path.stdout.strip():
        return []
    try:
        lines = (repo_path / log_path.stdout.strip()).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    tips: set[str] = set()
    for line in lines:
        for oid in line.split()[:2]:
            if _OID_RE.fullmatch(oid) and oid.strip("0"):
                tips.add(oid)
    return sorted(tips)


def _unpushed_commit_count(repo_path: Path, ref: str) -> int | None:
    """Commits of HEAD that are on no remote branch and were never on ``ref`` (None if git failed).

    Commits dropped from ``ref`` by a force-push were on the server, so they do not count.
    """
    seen_tips = _seen_upstream_tips(repo_path, ref)
    count = _git_run(["rev-list", "--count", "HEAD", "--not", "--remotes", *seen_tips], repo_path, timeout=15.0)
    if count.returncode != 0:
        return None
    try:
        return int(count.stdout.strip())
    except ValueError:
        return None


def _unpushed_commits_error(count: int | None, ref: str) -> str:
    return (
        f"В локальной ветке есть коммиты, которых нет на сервере git: {count if count is not None else '?'} "
        f"(история расходится с {ref}) — синхронизируйте вручную"
    )


def git_pull(repo_path: Path) -> dict[str, Any]:
    if not repo_path.is_dir() or not (repo_path / ".git").is_dir():
        return {"success": False, "output": "", "error": "Не git-репозиторий"}

    try:
        fetch = _git_run(["fetch", "origin"], repo_path, timeout=60.0)
        if fetch.returncode != 0:
            output = ((fetch.stdout or "") + (fetch.stderr or "")).strip()
            return {"success": False, "output": output, "error": output or "git fetch failed"}

        ref, ref_error = resolve_update_ref(repo_path)
        if ref is None:
            return {"success": False, "output": "", "error": ref_error}

        result = _git_run(["merge", "--ff-only", ref], repo_path)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if result.returncode == 0:
            return {"success": True, "output": output, "error": None, "method": "fast-forward"}

        # After force-push on origin the node copy may diverge while the tree is still clean.
        if _working_tree_clean(repo_path):
            unpushed = _unpushed_commit_count(repo_path, ref)
            if unpushed != 0:
                return {
                    "success": False,
                    "output": output,
                    "error": _unpushed_commits_error(unpushed, ref),
                    "method": "fast-forward",
                }
            reset = _git_run(["reset", "--hard", ref], repo_path)
            reset_output = ((reset.stdout or "") + (reset.stderr or "")).strip()
            if reset.returncode == 0:
                combined = "\n".join(
                    part for part in (output, f"История переписана: reset --hard {ref}", reset_output) if part
                )
                return {
                    "success": True,
                    "output": combined.strip(),
                    "error": None,
                    "method": "reset",
                }
            output = "\n".join(part for part in (output, reset_output) if part).strip()

        return {
            "success": False,
            "output": output,
            "error": output or "git pull failed",
            "method": "fast-forward",
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
    """Restart node agent after git pull via systemd."""
    log_path = _restart_log_path(repo_root)

    if not _systemd_unit_installed():
        message = f"Unit {SYSTEMD_UNIT} не установлен — systemctl restart недоступен"
        _append_restart_log(log_path, message)
        return {"method": "none", "success": False, "output": "", "error": message}

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
    agent_version: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    from app.services.node_health import NODE_AGENT_VERSION
    from app.services.systemd_refresh import refresh_installed_systemd_units

    agent_version = agent_version or NODE_AGENT_VERSION
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
            # 2.19+: rewrite unit before restart — old ExecStart=…/start_node_agent.sh breaks after pull.
            # Soft-fail on refresh: compat start_node_agent.sh shim still boots; migrate on startup.
            systemd_refresh = refresh_installed_systemd_units(repo_root, panel=False, node=True)
            detail["systemd_refresh"] = systemd_refresh
            if not systemd_refresh.get("success"):
                messages.append(
                    "Предупреждение systemd: "
                    + (systemd_refresh.get("error") or "не удалось обновить unit node")
                )
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
