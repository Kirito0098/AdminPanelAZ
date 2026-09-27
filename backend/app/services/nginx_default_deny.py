"""Сервер по умолчанию nginx (scripts/nginx-default-deny.sh): закрыт ли доступ к панели по IP сервера."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

RunCmd = Callable[[list[str], float], subprocess.CompletedProcess]
Mode = Literal["--check", "--apply"]

SCRIPT_NAME = "nginx-default-deny.sh"
CHECK_TIMEOUT = 10.0
APPLY_TIMEOUT = 60.0  # до 20 с ожидания flock параллельного --apply плюс nginx -t и reload
STATUSES = frozenset({"installed", "needed", "outdated", "own_default", "not_applicable"})
_LOG_PREFIXES = ("[nginx-setup] ОШИБКА: ", "[nginx-setup] ВНИМАНИЕ: ", "[nginx-setup] ")


@dataclass
class DefaultDenyResult:
    ok: bool
    status: str | None
    installed: bool = False
    changed: bool = False
    error: str = ""
    message: str = ""
    ports: list[dict] = field(default_factory=list)


def script_path(install_dir: str | Path) -> Path:
    return Path(install_dir) / "scripts" / SCRIPT_NAME


def is_nginx_publish_mode(env: dict[str, str]) -> bool:
    mode = (env.get("PUBLISH_MODE") or "").strip()
    if mode:
        return mode.startswith("nginx_")
    return (env.get("BEHIND_NGINX") or "").strip().lower() in ("1", "true", "yes", "on")


def _default_run_cmd(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _last_log_message(stderr: str) -> str:
    for raw in reversed((stderr or "").splitlines()):
        line = raw.strip()
        if not line:
            continue
        for prefix in _LOG_PREFIXES:
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
        return line
    return ""


def _parse_status_line(stdout: str) -> dict | None:
    for raw in reversed((stdout or "").splitlines()):
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            return None
        if isinstance(payload, dict) and payload.get("status") in STATUSES:
            return payload
        return None
    return None


def run_default_deny_script(
    path: str | Path,
    mode: Mode,
    *,
    run_cmd: RunCmd | None = None,
) -> DefaultDenyResult:
    """Запускает скрипт; ошибки запуска возвращаются в message, исключения наружу не летят."""
    script = Path(path)
    if not script.is_file():
        return DefaultDenyResult(ok=False, status=None, message=f"Скрипт {script} не найден — обновите панель")

    timeout = CHECK_TIMEOUT if mode == "--check" else APPLY_TIMEOUT
    runner = run_cmd or _default_run_cmd
    try:
        proc = runner(["bash", str(script), mode], timeout)
    except subprocess.TimeoutExpired:
        return DefaultDenyResult(ok=False, status=None, message=f"{script.name} не ответил за {timeout:.0f} с")
    except OSError as exc:
        return DefaultDenyResult(ok=False, status=None, message=f"Не удалось запустить {script.name}: {exc}")

    message = _last_log_message(proc.stderr or "")
    payload = _parse_status_line(proc.stdout or "")
    if payload is None:
        return DefaultDenyResult(
            ok=False,
            status=None,
            message=message or f"{script.name} завершился с кодом {proc.returncode} без результата",
        )
    ports = payload.get("ports")
    return DefaultDenyResult(
        ok=proc.returncode == 0,
        status=str(payload["status"]),
        installed=bool(payload.get("installed")),
        changed=bool(payload.get("changed")),
        error=str(payload.get("error") or ""),
        message=message,
        ports=[p for p in ports if isinstance(p, dict)] if isinstance(ports, list) else [],
    )
