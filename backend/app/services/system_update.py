"""Git-based self-update for AdminPanelAZ controller (UI «Обновления»)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from app.services.node_update import (
    git_pull,
    resolve_repo_root,
    schedule_restart,
    systemd_restart,
    systemd_unit_installed,
)
from app.services.systemd_refresh import refresh_installed_systemd_units

SYSTEMD_UNIT = "adminpanelaz"
ProgressCallback = Callable[[int, str], None] | None

PIP_TIMEOUT = 300.0
NPM_INSTALL_TIMEOUT = 600.0
NPM_BUILD_TIMEOUT = 900.0
# Скрипт сам ждёт свежую сборку до 2 минут (FRONTEND_ARTIFACT_ATTEMPTS × FRONTEND_ARTIFACT_RETRY_DELAY).
FRONTEND_ARTIFACT_TIMEOUT = 300.0
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
            "returncode": result.returncode,
            "output": output,
            "error": None if success else output or f"{label} failed (exit {result.returncode})",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "returncode": None, "output": "", "error": f"Таймаут: {label}"}
    except OSError as exc:
        return {"success": False, "returncode": None, "output": "", "error": str(exc)}


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
    reused = frontend_build_reused(repo_root)
    if reused:
        return {"skipped": True, "success": True, "output": f"{reused} — npm ci пропущен"}
    result = _run_command(
        ["npm", "ci"],
        cwd=frontend_dir,
        timeout=NPM_INSTALL_TIMEOUT,
        label="npm ci",
    )
    result["skipped"] = False
    return result


def build_frontend(repo_root: Path, *, force: bool = False) -> dict[str, Any]:
    frontend_dir = repo_root / "frontend"
    package_json = frontend_dir / "package.json"
    if not package_json.is_file():
        return {"skipped": True, "success": True, "output": "frontend/package.json не найден"}
    if not force:
        reused = frontend_build_reused(repo_root)
        if reused:
            return {"skipped": True, "success": True, "output": f"{reused} — npm run build:all пропущен"}
    result = _run_command(
        ["npm", "run", "build:all"],
        cwd=frontend_dir,
        timeout=NPM_BUILD_TIMEOUT,
        label="npm run build:all",
    )
    # Собрали на месте — метка CI больше не описывает dist.
    (frontend_dir / "dist" / ".build-info.json").unlink(missing_ok=True)
    result["skipped"] = False
    return result


def install_frontend_artifact(repo_root: Path, *, reuse_local: bool = True) -> dict[str, Any]:
    """Готовый интерфейс из GitHub (канал frontend-builds) без npm на сервере.

    Коды scripts/panel-frontend-deploy.sh: 0 — поставлено, 3 — сборки нет,
    4 — канал недоступен, 1 — не прошло проверку. reuse_local=False — переустановить,
    даже если dist уже помечен текущим коммитом (кнопка «Переустановить интерфейс»).
    """
    script = repo_root / "scripts" / "panel-frontend-deploy.sh"
    if not script.is_file():
        return {"skipped": True, "success": False, "returncode": None, "output": "scripts/panel-frontend-deploy.sh не найден"}
    head = _git_head(repo_root)
    if not head:
        return {"skipped": True, "success": False, "returncode": None, "output": "не удалось определить коммит HEAD"}
    if reuse_local:
        reused = frontend_build_reused(repo_root)
        if reused:
            return {"skipped": True, "success": True, "returncode": 0, "output": f"{reused} — загрузка пропущена"}
    result = _run_command(
        ["bash", str(script), "--commit", head, "--dir", str(repo_root), "--no-restart"],
        cwd=repo_root,
        timeout=FRONTEND_ARTIFACT_TIMEOUT,
        label="panel-frontend-deploy.sh",
    )
    result["skipped"] = False
    code = result.get("returncode")
    if code == 0:
        result["output"] = result.get("output") or f"готовый интерфейс поставлен из GitHub (коммит {head[:12]})"
        result["error"] = None
    elif code in (3, 4):
        result["success"] = False
        result["error"] = f"готовой сборки нет (код {code})"
    else:
        result["success"] = False
        result["error"] = f"готовая сборка не прошла проверку (код {code})"
    return result


def _git_head(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def frontend_build_reused(repo_root: Path) -> str | None:
    """Интерфейс уже собран для текущего коммита сборкой из CI (frontend/dist/.build-info.json)."""
    frontend_dist = repo_root / "frontend" / "dist"
    if not (frontend_dist / "index.html").is_file():
        return None
    try:
        info = json.loads((frontend_dist / ".build-info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    commit = info.get("commit") if isinstance(info, dict) else None
    head = _git_head(repo_root)
    if not isinstance(commit, str) or not commit or commit != head:
        return None
    return f"интерфейс уже собран для коммита {commit[:12]} (.build-info.json)"


def _restart_log_path(repo_root: Path) -> Path:
    state = os.environ.get("ADMINPANELAZ_STATE_DIR")
    if state:
        return Path(state) / "logs" / "update-restart.log"
    return repo_root / ".runtime" / "logs" / "update-restart.log"


def _systemd_unit_installed(unit: str = SYSTEMD_UNIT) -> bool:
    return systemd_unit_installed(unit)


def restart_controller(repo_root: Path) -> dict[str, Any]:
    """Restart controller after update via systemd."""
    return systemd_restart(SYSTEMD_UNIT, _restart_log_path(repo_root))


def schedule_controller_restart(repo_root: Path, *, delay_seconds: float = RESTART_DELAY_SECONDS) -> None:
    schedule_restart(SYSTEMD_UNIT, _restart_log_path(repo_root), delay_seconds)


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

    report(50, "Обновление: готовый интерфейс из GitHub…")
    artifact = install_frontend_artifact(repo_root)
    detail["frontend_artifact"] = artifact
    if artifact.get("success"):
        output_parts.append(f"[frontend] {artifact.get('output') or 'интерфейс уже собран'}")
    else:
        # Канала нет (нет сборки, не GitHub, нет сети) — прежняя сборка на сервере.
        if artifact.get("output") or artifact.get("error"):
            output_parts.append(f"[frontend] {artifact.get('output') or artifact.get('error')} — сборка на сервере")
        report(55, "Обновление: npm ci…")
        npm_install = install_frontend_requirements(repo_root)
        detail["npm_install"] = npm_install
        if not _require_step(label="npm ci", result=npm_install, output_parts=output_parts, errors=errors):
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

    # Rewrite units before restart: a unit with legacy ExecStart=…/start.sh no longer boots.
    # Soft-fail: pull/build already succeeded; units on systemd-exec-*.sh restart fine without refresh.
    report(85, "Обновление: systemd units…")
    systemd_refresh = refresh_installed_systemd_units(repo_root, panel=True, node=True)
    detail["systemd_refresh"] = systemd_refresh
    if systemd_refresh.get("output"):
        output_parts.append(f"[systemd]\n{systemd_refresh['output']}")
    if not systemd_refresh.get("success"):
        warn = systemd_refresh.get("error") or "Ошибка обновления systemd units"
        output_parts.append(
            f"[systemd] Предупреждение: {warn}. "
            "Перезапуск всё равно запланирован."
        )

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


def apply_controller_rebuild(
    *,
    repo_root: Path | None = None,
    progress: ProgressCallback = None,
) -> dict[str, Any]:
    """Переустановить интерфейс (готовый архив из GitHub, иначе npm run build:all) и перезапустить панель."""
    repo_root = repo_root or resolve_repo_root()
    report = progress or _noop_progress
    output_parts: list[str] = []
    errors: list[str] = []
    detail: dict[str, Any] = {}
    restarting = False

    if not repo_root:
        return {
            "success": False,
            "message": "Пересборка не выполнена",
            "errors": ["Репозиторий AdminPanelAZ не найден"],
            "output": "",
            "restarting": False,
            "detail": detail,
        }

    report(15, "Переустановка: готовый интерфейс из GitHub…")
    artifact = install_frontend_artifact(repo_root, reuse_local=False)
    detail["frontend_artifact"] = artifact
    if artifact.get("success"):
        output_parts.append(f"[frontend] {artifact.get('output') or 'интерфейс переустановлен из GitHub'}")
    else:
        if artifact.get("output") or artifact.get("error"):
            output_parts.append(f"[frontend] {artifact.get('output') or artifact.get('error')} — сборка на сервере")
        report(30, "Переустановка: сборка frontend…")
        npm_build = build_frontend(repo_root, force=True)
        detail["npm_build"] = npm_build
        if not _require_step(label="npm run build:all", result=npm_build, output_parts=output_parts, errors=errors):
            return {
                "success": False,
                "message": "Пересборка не выполнена",
                "errors": errors,
                "output": "\n\n".join(output_parts).strip(),
                "restarting": False,
                "detail": detail,
            }

    report(90, "Пересборка: перезапуск панели…")
    schedule_controller_restart(repo_root)
    restarting = True
    output_parts.append("[restart] Перезапуск adminpanelaz запланирован через несколько секунд")

    report(100, "Переустановка завершена")
    return {
        "success": True,
        "message": "Интерфейс переустановлен, панель перезапускается",
        "errors": [],
        "output": "\n\n".join(output_parts).strip(),
        "restarting": restarting,
        "detail": detail,
    }
