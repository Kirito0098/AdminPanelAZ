"""Git-based self-update for AdminPanelAZ controller (UI «Обновления»)."""

from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.services.node_update import git_pull, resolve_repo_root

SYSTEMD_UNIT = "adminpanelaz"
ProgressCallback = Callable[[int, str], None] | None

PIP_TIMEOUT = 300.0
NPM_INSTALL_TIMEOUT = 600.0
NPM_BUILD_TIMEOUT = 900.0
RESTART_DELAY_SECONDS = 2.0


def _noop_progress(_percent: int, _stage: str) -> None:
    return None


def ensure_backend_data_dirs(repo_root: Path) -> None:
    backend_data = repo_root / "backend" / "data"
    for relative in ("", "cidr", "cidr/list", "cidr/staging"):
        (backend_data / relative).mkdir(parents=True, exist_ok=True)


def _run_command(
    args: list[str],
    *,
    cwd: Path,
    timeout: float,
    label: str,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        success = result.returncode == 0
        return {
            "success": success,
            "output": output,
            "error": None if success else output or f"{label} failed (exit {result.returncode})",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": f"Таймаут: {label}"}
    except OSError as exc:
        return {"success": False, "output": "", "error": str(exc)}


def install_backend_requirements(repo_root: Path) -> dict[str, Any]:
    venv_pip = repo_root / "backend" / ".venv" / "bin" / "pip"
    requirements = repo_root / "backend" / "requirements.txt"
    if not venv_pip.is_file() or not requirements.is_file():
        return {"skipped": True, "success": True, "output": "backend/.venv или requirements.txt не найдены"}
    result = _run_command(
        [str(venv_pip), "install", "-q", "-r", str(requirements)],
        cwd=repo_root,
        timeout=PIP_TIMEOUT,
        label="pip install",
    )
    result["skipped"] = False
    return result


def install_frontend_requirements(repo_root: Path) -> dict[str, Any]:
    frontend_dir = repo_root / "frontend"
    package_json = frontend_dir / "package.json"
    if not package_json.is_file():
        return {"skipped": True, "success": True, "output": "frontend/package.json не найден"}
    result = _run_command(
        ["npm", "install"],
        cwd=frontend_dir,
        timeout=NPM_INSTALL_TIMEOUT,
        label="npm install",
    )
    result["skipped"] = False
    return result


def build_frontend(repo_root: Path) -> dict[str, Any]:
    frontend_dir = repo_root / "frontend"
    package_json = frontend_dir / "package.json"
    if not package_json.is_file():
        return {"skipped": True, "success": True, "output": "frontend/package.json не найден"}
    result = _run_command(
        ["npm", "run", "build:all"],
        cwd=frontend_dir,
        timeout=NPM_BUILD_TIMEOUT,
        label="npm run build:all",
    )
    result["skipped"] = False
    return result


def _restart_log_path(repo_root: Path) -> Path:
    state = os.environ.get("ADMINPANELAZ_STATE_DIR")
    if state:
        return Path(state) / "logs" / "update-restart.log"
    return repo_root / ".runtime" / "logs" / "update-restart.log"


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


def restart_controller(repo_root: Path) -> dict[str, Any]:
    """Restart controller after update. Prefer systemd when the unit is installed."""
    log_path = _restart_log_path(repo_root)
    script = repo_root / "start.sh"

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
            "error": None if success else output or "start.sh restart failed",
        }
    except (subprocess.TimeoutExpired, OSError) as exc:
        _append_restart_log(log_path, f"{script} restart: {exc}")
        return {"method": "script", "success": False, "output": "", "error": str(exc)}


def schedule_controller_restart(repo_root: Path, *, delay_seconds: float = RESTART_DELAY_SECONDS) -> None:
    def _restart() -> None:
        restart_controller(repo_root)

    timer = threading.Timer(delay_seconds, _restart)
    timer.daemon = True
    timer.start()


def _require_step(
    *,
    label: str,
    result: dict[str, Any],
    output_parts: list[str],
    errors: list[str],
) -> bool:
    if result.get("skipped"):
        if result.get("output"):
            output_parts.append(f"[{label}] {result['output']}")
        return True
    if result.get("output"):
        output_parts.append(f"[{label}]\n{result['output']}")
    if result.get("success"):
        return True
    errors.append(result.get("error") or f"Ошибка: {label}")
    return False


def apply_controller_update(
    *,
    repo_root: Path | None = None,
    progress: ProgressCallback = None,
) -> dict[str, Any]:
    """Pull main, refresh deps, rebuild frontend, schedule panel restart."""
    repo_root = repo_root or resolve_repo_root()
    report = progress or _noop_progress
    output_parts: list[str] = []
    errors: list[str] = []
    detail: dict[str, Any] = {}
    restarting = False

    if not repo_root:
        return {
            "success": False,
            "message": "Обновление не выполнено",
            "errors": ["Репозиторий AdminPanelAZ не найден"],
            "output": "",
            "restarting": False,
            "detail": detail,
        }

    report(10, "Обновление: git fetch / pull…")
    pull = git_pull(repo_root)
    detail["git_pull"] = pull
    if pull.get("output"):
        output_parts.append(f"[git pull]\n{pull['output']}")
    if not pull.get("success"):
        errors.append(pull.get("error") or "Ошибка git pull")
        return {
            "success": False,
            "message": "Обновление не выполнено",
            "errors": errors,
            "output": "\n\n".join(output_parts).strip(),
            "restarting": False,
            "detail": detail,
        }

    report(25, "Обновление: каталоги данных…")
    ensure_backend_data_dirs(repo_root)
    output_parts.append("[data dirs] backend/data/cidr подготовлены")

    report(35, "Обновление: pip install…")
    pip_result = install_backend_requirements(repo_root)
    detail["pip"] = pip_result
    if not _require_step(label="pip install", result=pip_result, output_parts=output_parts, errors=errors):
        return {
            "success": False,
            "message": "Обновление не выполнено",
            "errors": errors,
            "output": "\n\n".join(output_parts).strip(),
            "restarting": False,
            "detail": detail,
        }

    report(50, "Обновление: npm install…")
    npm_install = install_frontend_requirements(repo_root)
    detail["npm_install"] = npm_install
    if not _require_step(label="npm install", result=npm_install, output_parts=output_parts, errors=errors):
        return {
            "success": False,
            "message": "Обновление не выполнено",
            "errors": errors,
            "output": "\n\n".join(output_parts).strip(),
            "restarting": False,
            "detail": detail,
        }

    report(70, "Обновление: сборка frontend…")
    npm_build = build_frontend(repo_root)
    detail["npm_build"] = npm_build
    if not _require_step(label="npm run build:all", result=npm_build, output_parts=output_parts, errors=errors):
        return {
            "success": False,
            "message": "Обновление не выполнено",
            "errors": errors,
            "output": "\n\n".join(output_parts).strip(),
            "restarting": False,
            "detail": detail,
        }

    report(90, "Обновление: перезапуск панели…")
    schedule_controller_restart(repo_root)
    restarting = True
    output_parts.append("[restart] Перезапуск adminpanelaz запланирован через несколько секунд")

    report(100, "Обновление завершено")
    return {
        "success": True,
        "message": "Обновление применено, панель перезапускается",
        "errors": [],
        "output": "\n\n".join(output_parts).strip(),
        "restarting": restarting,
        "detail": detail,
    }
