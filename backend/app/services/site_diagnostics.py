"""Диагностика запуска панели: systemd, файлы, порт, HTTP, nginx."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.services.firewall_tools_check import apt_install_hint, check_firewall_tools

Status = Literal["ok", "warn", "fail"]
RunCategory = Literal["systemd", "files", "https", "port", "http", "nginx", "firewall", "summary"]
RunCmd = Callable[[list[str], float], subprocess.CompletedProcess]

RUNBOOK_STEPS: list[dict[str, str]] = [
    {
        "id": "systemd",
        "title": "Systemd сервис",
        "description": "Unit-файл, автозагрузка, состояние и journal",
    },
    {
        "id": "files",
        "title": "Файлы проекта",
        "description": ".env, база данных, venv и скрипты запуска",
    },
    {
        "id": "https",
        "title": "HTTPS и домен",
        "description": "BEHIND_NGINX, ENFORCE_HTTPS и DOMAIN в .env",
    },
    {
        "id": "port",
        "title": "Порт backend",
        "description": "Слушает ли uvicorn BACKEND_PORT",
    },
    {
        "id": "http",
        "title": "HTTP-проверка",
        "description": "Ответ /api/health на localhost",
    },
    {
        "id": "nginx",
        "title": "Nginx reverse-proxy",
        "description": "Конфиг, proxy_pass и nginx -t",
    },
    {
        "id": "firewall",
        "title": "Firewall tools",
        "description": "iptables и ipset для защиты панели",
    },
    {
        "id": "summary",
        "title": "Итог",
        "description": "Сводка и рекомендуемые команды",
    },
]


@dataclass
class CheckResult:
    status: Status
    title: str
    detail: str = ""
    hint_ru: str = ""
    category: RunCategory = "summary"


@dataclass
class DiagnosticsContext:
    install_dir: str
    service_name: str = "adminpanelaz"
    venv_path: str | None = None

    def backend_dir(self) -> str:
        return os.path.join(self.install_dir, "backend")

    def resolved_venv(self) -> str:
        if self.venv_path:
            return self.venv_path
        return os.path.join(self.backend_dir(), ".venv")


@dataclass
class DiagnosticsReport:
    results: list[CheckResult] = field(default_factory=list)
    recommended_commands: list[str] = field(default_factory=list)
    _current_category: RunCategory = field(default="summary", repr=False, compare=False)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if r.status == "warn")

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    def has_failures(self) -> bool:
        return self.fail_count > 0


# regex → подсказка (Debian/Ubuntu); {port} подставляется из контекста вызова
ERROR_HINTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"Address already in use", re.I),
        "Порт {port} занят другим процессом. Проверка: ss -tlnp | grep ':{port}'",
    ),
    (
        re.compile(r"(ModuleNotFoundError|ImportError)", re.I),
        "Не хватает Python-зависимостей. Установите: venv/bin/pip install -r requirements.txt",
    ),
    (
        re.compile(r"Permission denied", re.I),
        "Нет прав на backend/.env, data/adminpanel.db или каталог WorkingDirectory. "
        "Проверьте владельца и chmod/chown.",
    ),
    (
        re.compile(r"No such file.*(cert|key|ssl|\.pem)", re.I),
        "Файлы SSL не найдены. Настройте nginx/Let's Encrypt (scripts/nginx-setup.sh) или проверьте DOMAIN.",
    ),
    (
        re.compile(r"status=203/EXEC", re.I),
        "Исполняемый файл не найден (часто start.sh или backend/.venv/bin/uvicorn). Пересоздайте venv.",
    ),
    (
        re.compile(r"(OOM|Out of memory|Killed process|killed)", re.I),
        "Нехватка RAM. Уменьшите UVICORN_WORKERS или добавьте swap.",
    ),
    (
        re.compile(r"(Failed to bind|Can't connect|Connection refused)", re.I),
        "Проблема BACKEND_HOST/BACKEND_PORT или firewall. Проверьте backend/.env: ufw status",
    ),
]


def decode_journal_line(line: str, *, app_port: str = "8000") -> str | None:
    """Возвращает подсказку по строке journal, если распознана ошибка."""
    text = (line or "").strip()
    if not text:
        return None
    for pattern, hint in ERROR_HINTS:
        if pattern.search(text):
            return hint.format(port=app_port)
    return None


def _default_run_cmd(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _read_env_file(env_path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not os.path.isfile(env_path):
        return values
    with open(env_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _env_bool(value: str | None) -> bool:
    return (value or "").lower() in ("1", "true", "yes", "on")


def _set_category(report: DiagnosticsReport, category: RunCategory) -> None:
    report._current_category = category


def _append_result(report: DiagnosticsReport, result: CheckResult) -> None:
    result.category = report._current_category
    report.results.append(result)


def resolve_diagnostics_context(
    *,
    install_dir: str | None = None,
    service_name: str | None = None,
    venv_path: str | None = None,
) -> DiagnosticsContext:
    from pathlib import Path

    from app.config import get_settings

    app_root = Path(__file__).resolve().parents[2]
    resolved_install = install_dir or os.environ.get("INSTALL_DIR") or str(app_root.parent)
    settings = get_settings()
    raw_service = service_name or os.environ.get("SERVICE_NAME") or settings.admin_panel_az_service_name
    resolved_service = raw_service.removesuffix(".service")
    resolved_venv = (
        venv_path
        or os.environ.get("VENV_PATH")
        or os.path.join(resolved_install, "backend", ".venv")
    )
    return DiagnosticsContext(
        install_dir=resolved_install,
        service_name=resolved_service,
        venv_path=resolved_venv,
    )


def _step_status(results: list[CheckResult]) -> Status:
    if any(r.status == "fail" for r in results):
        return "fail"
    if any(r.status == "warn" for r in results):
        return "warn"
    if results:
        return "ok"
    return "ok"


def _check_result_dict(result: CheckResult) -> dict[str, str]:
    payload: dict[str, str] = {
        "status": result.status,
        "title": result.title,
        "category": result.category,
    }
    if result.detail:
        payload["detail"] = result.detail
    if result.hint_ru:
        payload["hint_ru"] = result.hint_ru
    return payload


def report_to_dict(report: DiagnosticsReport, ctx: DiagnosticsContext) -> dict:
    by_category: dict[str, list[CheckResult]] = {step["id"]: [] for step in RUNBOOK_STEPS}
    for result in report.results:
        by_category.setdefault(result.category, []).append(result)

    steps = []
    for step_def in RUNBOOK_STEPS:
        step_id = step_def["id"]
        step_results = by_category.get(step_id, [])
        steps.append(
            {
                **step_def,
                "status": _step_status(step_results),
                "checks": [_check_result_dict(r) for r in step_results],
            }
        )

    return {
        "success": not report.has_failures(),
        "install_dir": ctx.install_dir,
        "service_name": ctx.service_name,
        "summary": {
            "ok": report.ok_count,
            "warn": report.warn_count,
            "fail": report.fail_count,
            "has_failures": report.has_failures(),
        },
        "steps": steps,
        "results": [_check_result_dict(r) for r in report.results],
        "recommended_commands": list(report.recommended_commands),
    }


def _check_systemd(
    ctx: DiagnosticsContext,
    env: dict[str, str],
    report: DiagnosticsReport,
    run_cmd: RunCmd,
) -> None:
    unit_path = f"/etc/systemd/system/{ctx.service_name}.service"
    app_port = env.get("BACKEND_PORT", env.get("APP_PORT", "8000"))

    if os.path.isfile(unit_path):
        _append_result(
            report,
            CheckResult("ok", f"Unit-файл {ctx.service_name}.service найден"),
        )
    else:
        _append_result(
            report,
            CheckResult(
                "fail",
                f"Unit-файл {ctx.service_name}.service не найден",
                detail=unit_path,
                hint_ru="Переустановите панель или создайте unit через install.",
            ),
        )
        report.recommended_commands.append(
            f"journalctl -u {ctx.service_name} -n 50 --no-pager"
        )
        return

    enabled = run_cmd(["systemctl", "is-enabled", ctx.service_name], 5.0)
    enabled_out = (enabled.stdout or enabled.stderr or "").strip()
    if enabled.returncode == 0 and enabled_out in ("enabled", "enabled-runtime"):
        _append_result(report, CheckResult("ok", "Сервис включён в автозагрузку (enabled)"))
    else:
        _append_result(
            report,
            CheckResult(
                "warn",
                "Сервис не в автозагрузке",
                detail=enabled_out or f"exit {enabled.returncode}",
                hint_ru=f"systemctl enable {ctx.service_name}",
            ),
        )

    active = run_cmd(["systemctl", "is-active", ctx.service_name], 5.0)
    active_out = (active.stdout or "").strip()
    if active.returncode == 0 and active_out == "active":
        _append_result(report, CheckResult("ok", f"Сервис {ctx.service_name} запущен (active)"))
    else:
        detail = (active.stderr or active.stdout or "").strip() or f"состояние: {active_out}"
        _append_result(
            report,
            CheckResult(
                "fail",
                f"Сервис {ctx.service_name} не запущен",
                detail=detail,
                hint_ru=f"systemctl restart {ctx.service_name}",
            ),
        )
        report.recommended_commands.append(f"systemctl restart {ctx.service_name}")

    journal = run_cmd(
        ["journalctl", "-u", ctx.service_name, "-n", "30", "--no-pager", "-o", "cat"],
        10.0,
    )
    journal_text = (journal.stdout or "") + (journal.stderr or "")
    decoded_hints: list[str] = []
    for line in journal_text.splitlines():
        hint = decode_journal_line(line, app_port=app_port)
        if hint and hint not in decoded_hints:
            decoded_hints.append(hint)

    if decoded_hints:
        _append_result(
            report,
            CheckResult(
                "warn" if active_out == "active" else "fail",
                "Расшифровка последних строк journal",
                detail="; ".join(decoded_hints[:3]),
                hint_ru=decoded_hints[0],
            ),
        )
    elif journal_text.strip():
        _append_result(
            report,
            CheckResult("ok", "Журнал systemd прочитан (последние 30 строк)"),
        )


def _check_project_files(ctx: DiagnosticsContext, report: DiagnosticsReport) -> dict[str, str]:
    install = ctx.install_dir
    backend = ctx.backend_dir()
    env_path = os.path.join(backend, ".env")
    db_path = os.path.join(backend, "data", "adminpanel.db")
    uvicorn_bin = os.path.join(ctx.resolved_venv(), "bin", "uvicorn")
    start_sh = os.path.join(install, "start.sh")
    main_py = os.path.join(backend, "app", "main.py")
    env: dict[str, str] = {}

    if os.path.isfile(env_path):
        _append_result(report, CheckResult("ok", "backend/.env найден"))
        env = _read_env_file(env_path)
        if env.get("SECRET_KEY"):
            _append_result(report, CheckResult("ok", "SECRET_KEY задан в .env"))
        else:
            _append_result(
                report,
                CheckResult(
                    "fail",
                    "SECRET_KEY не задан в .env",
                    hint_ru="Добавьте SECRET_KEY=... в backend/.env (openssl rand -hex 32).",
                ),
            )
    else:
        _append_result(
            report,
            CheckResult(
                "fail",
                "backend/.env не найден",
                detail=env_path,
                hint_ru="Создайте .env при установке или скопируйте из резервной копии.",
            ),
        )

    if os.path.isfile(db_path):
        _append_result(report, CheckResult("ok", "База adminpanel.db найдена"))
    else:
        _append_result(
            report,
            CheckResult(
                "fail",
                "База backend/data/adminpanel.db не найдена",
                detail=db_path,
                hint_ru="Запустите панель для инициализации БД или восстановите из бэкапа.",
            ),
        )

    if os.path.isfile(uvicorn_bin) and os.access(uvicorn_bin, os.X_OK):
        _append_result(report, CheckResult("ok", "backend/.venv/bin/uvicorn доступен"))
    else:
        _append_result(
            report,
            CheckResult(
                "fail",
                "backend/.venv/bin/uvicorn не найден или не исполняемый",
                detail=uvicorn_bin,
                hint_ru="cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt",
            ),
        )

    if os.path.isfile(start_sh) and os.access(start_sh, os.X_OK):
        _append_result(report, CheckResult("ok", "start.sh найден"))
    else:
        _append_result(
            report,
            CheckResult(
                "fail",
                "start.sh не найден или не исполняемый",
                detail=start_sh,
            ),
        )

    if os.path.isfile(main_py):
        _append_result(report, CheckResult("ok", "backend/app/main.py найден"))
    else:
        _append_result(
            report,
            CheckResult(
                "fail",
                "backend/app/main.py не найден",
                detail=main_py,
            ),
        )

    return env


def _check_https(env: dict[str, str], report: DiagnosticsReport) -> None:
    behind_nginx = _env_bool(env.get("BEHIND_NGINX"))
    enforce_https = _env_bool(env.get("ENFORCE_HTTPS"))
    domain = (env.get("DOMAIN") or "").strip()

    if not behind_nginx and not enforce_https:
        _append_result(
            report,
            CheckResult("ok", "Публикация через nginx не включена (BEHIND_NGINX не true)"),
        )
        return

    if domain:
        _append_result(report, CheckResult("ok", f"DOMAIN задан: {domain}"))
    else:
        _append_result(
            report,
            CheckResult(
                "warn",
                "BEHIND_NGINX/ENFORCE_HTTPS без DOMAIN",
                hint_ru="Задайте DOMAIN в backend/.env (scripts/nginx-setup.sh).",
            ),
        )


def _parse_ss_listeners(ss_output: str, port: str) -> list[str]:
    listeners: list[str] = []
    port_marker = f":{port}"
    for line in ss_output.splitlines():
        if port_marker not in line:
            continue
        listeners.append(line.strip())
    return listeners


def _check_port(
    env: dict[str, str],
    report: DiagnosticsReport,
    run_cmd: RunCmd,
) -> None:
    app_port = env.get("BACKEND_PORT", env.get("APP_PORT", "8000"))
    bind = env.get("BIND", "0.0.0.0")

    ss = run_cmd(["ss", "-tlnp"], 5.0)
    if ss.returncode != 0:
        _append_result(
            report,
            CheckResult(
                "warn",
                "Не удалось выполнить ss -tlnp",
                detail=(ss.stderr or ss.stdout or "").strip(),
                hint_ru="Установите iproute2: apt install iproute2",
            ),
        )
        return

    listeners = _parse_ss_listeners(ss.stdout or "", app_port)
    if not listeners:
        _append_result(
            report,
            CheckResult(
                "fail",
                f"Порт {app_port} не слушается",
                detail=f"BIND={bind}",
                hint_ru=(
                    f"Запустите сервис: systemctl restart adminpanelaz. "
                    f"Проверка: ss -tlnp | grep ':{app_port}'"
                ),
            ),
        )
        return

    uvicorn_lines = [ln for ln in listeners if re.search(r"uvicorn|python", ln, re.I)]
    foreign_lines = [ln for ln in listeners if ln not in uvicorn_lines]

    if uvicorn_lines:
        _append_result(
            report,
            CheckResult(
                "ok",
                f"Порт {app_port} слушает uvicorn",
                detail=uvicorn_lines[0][:200],
            ),
        )
    elif listeners:
        _append_result(
            report,
            CheckResult(
                "fail",
                f"Порт {app_port} занят другим процессом",
                detail=listeners[0][:200],
                hint_ru=(
                    f"Измените BACKEND_PORT в backend/.env или остановите чужой процесс. "
                    f"ss -tlnp | grep ':{app_port}'"
                ),
            ),
        )
        report.recommended_commands.append(f"ss -tlnp | grep ':{app_port}'")

    if foreign_lines and uvicorn_lines:
        _append_result(
            report,
            CheckResult("warn", "На порту несколько слушателей", detail=foreign_lines[0][:200]),
        )


def _http_probe_url(port: str) -> str:
    return f"http://127.0.0.1:{port}/api/health"


def _check_http_probe(
    env: dict[str, str],
    report: DiagnosticsReport,
    run_cmd: RunCmd,
) -> None:
    app_port = env.get("BACKEND_PORT", env.get("APP_PORT", "8000"))
    url = _http_probe_url(app_port)

    if _env_bool(env.get("BEHIND_NGINX")):
        _append_result(
            report,
            CheckResult(
                "warn",
                "HTTP-probe на 127.0.0.1 пропущен (BEHIND_NGINX=true)",
                detail="Проверьте nginx и HTTPS отдельно",
            ),
        )
        return

    last_err = ""
    probes: list[list[str]] = []
    if shutil.which("curl"):
        probes.append(["curl", "-sf", "--max-time", "3", url])
    if shutil.which("wget"):
        probes.append(["wget", "-q", "-O", "/dev/null", "--timeout=3", url])

    for cmd in probes:
        proc = run_cmd(cmd, 5.0)
        if proc.returncode == 0:
            _append_result(
                report,
                CheckResult("ok", f"HTTP ответ с {url}", detail="curl/wget успешно"),
            )
            return
        last_err = (proc.stderr or proc.stdout or "").strip()

    if not probes:
        _append_result(
            report,
            CheckResult(
                "warn",
                "HTTP-probe пропущен: нет curl и wget",
                hint_ru="apt install curl",
            ),
        )
        return

    _append_result(
        report,
        CheckResult(
            "fail",
            f"Нет HTTP-ответа от {url}",
            detail=last_err,
            hint_ru="Проверьте journalctl и что uvicorn слушает BACKEND_PORT.",
        ),
    )


def _nginx_site_path(domain: str) -> str:
    safe = domain.replace(".", "_")
    return f"/etc/nginx/sites-available/{safe}"


def _check_nginx(
    env: dict[str, str],
    report: DiagnosticsReport,
    run_cmd: RunCmd,
) -> None:
    domain = (env.get("DOMAIN") or "").strip()
    if not domain:
        _append_result(report, CheckResult("ok", "DOMAIN не задан — проверка nginx пропущена"))
        return

    app_port = env.get("BACKEND_PORT", env.get("APP_PORT", "8000"))
    conf_path = _nginx_site_path(domain)

    if os.path.isfile(conf_path):
        _append_result(report, CheckResult("ok", f"Конфиг nginx: {conf_path}"))
    else:
        _append_result(
            report,
            CheckResult(
                "warn",
                "Конфиг nginx для DOMAIN не найден",
                detail=conf_path,
                hint_ru="Настройте reverse-proxy или уберите DOMAIN из .env.",
            ),
        )
        return

    with open(conf_path, encoding="utf-8") as fh:
        conf_text = fh.read()

    expected = f"proxy_pass http://127.0.0.1:{app_port}"
    if expected in conf_text or f"127.0.0.1:{app_port}" in conf_text:
        _append_result(
            report,
            CheckResult("ok", f"proxy_pass указывает на порт {app_port}"),
        )
    else:
        _append_result(
            report,
            CheckResult(
                "warn",
                f"proxy_pass может не указывать на порт {app_port}",
                hint_ru=f"Проверьте proxy_pass http://127.0.0.1:{app_port} в {conf_path}",
            ),
        )

    nginx_t = run_cmd(["nginx", "-t"], 10.0)
    combined = ((nginx_t.stdout or "") + (nginx_t.stderr or "")).strip()
    if nginx_t.returncode == 0:
        _append_result(report, CheckResult("ok", "nginx -t успешно"))
    else:
        _append_result(
            report,
            CheckResult(
                "fail",
                "nginx -t завершился с ошибкой",
                detail=combined[:300],
                hint_ru="Исправьте синтаксис конфига и: systemctl reload nginx",
            ),
        )

    nginx_active = run_cmd(["systemctl", "is-active", "nginx"], 5.0)
    if (nginx_active.stdout or "").strip() == "active":
        _append_result(report, CheckResult("ok", "Сервис nginx активен"))
    else:
        _append_result(
            report,
            CheckResult(
                "warn",
                "Сервис nginx не активен",
                detail=(nginx_active.stderr or nginx_active.stdout or "").strip(),
                hint_ru="systemctl start nginx && systemctl enable nginx",
            ),
        )


def _build_summary(report: DiagnosticsReport, ctx: DiagnosticsContext) -> None:
    summary_detail = (
        f"ok={report.ok_count}, warn={report.warn_count}, fail={report.fail_count}"
    )
    if report.has_failures():
        status: Status = "fail"
        title = "Диагностика завершена с ошибками"
    elif report.warn_count:
        status = "warn"
        title = "Диагностика завершена с предупреждениями"
    else:
        status = "ok"
        title = "Диагностика: критических проблем не найдено"

    _append_result(report, CheckResult(status, title, detail=summary_detail))

    base_cmds = [
        f"systemctl restart {ctx.service_name}",
        f"journalctl -u {ctx.service_name} -n 50 --no-pager",
    ]
    for cmd in base_cmds:
        if cmd not in report.recommended_commands:
            report.recommended_commands.append(cmd)

    diag_cmd = f"{ctx.install_dir}/scripts/site-diagnostics.sh"
    if diag_cmd not in report.recommended_commands:
        report.recommended_commands.append(diag_cmd)


def run_site_diagnostics(
    ctx: DiagnosticsContext,
    *,
    run_cmd: RunCmd | None = None,
) -> DiagnosticsReport:
    """Последовательная диагностика запуска сайта."""
    runner = run_cmd or _default_run_cmd
    report = DiagnosticsReport()

    env_path = os.path.join(ctx.backend_dir(), ".env")
    env = _read_env_file(env_path) if os.path.isfile(env_path) else {}

    _set_category(report, "systemd")
    _check_systemd(ctx, env, report, runner)
    _set_category(report, "files")
    env = _check_project_files(ctx, report)
    _set_category(report, "https")
    _check_https(env, report)
    _set_category(report, "port")
    _check_port(env, report, runner)
    _set_category(report, "http")
    _check_http_probe(env, report, runner)
    _set_category(report, "nginx")
    _check_nginx(env, report, runner)
    _set_category(report, "firewall")
    _check_firewall_tools(report, runner)
    _set_category(report, "summary")
    _build_summary(report, ctx)

    return report


def _check_firewall_tools(report: DiagnosticsReport, runner: RunCmd) -> None:
    fw = check_firewall_tools(run_cmd=runner)
    if fw.fully_ready:
        _append_result(
            report,
            CheckResult("ok", "iptables и ipset", detail=fw.operational_detail),
        )
        return

    parts: list[str] = []
    if fw.missing_commands:
        parts.append(f"нет команд: {', '.join(fw.missing_commands)}")
    if fw.missing_packages:
        parts.append(f"нет пакетов: {', '.join(fw.missing_packages)}")
    if fw.binaries_available and not fw.operational_ok:
        parts.append(fw.operational_detail)
    hint_pkgs = fw.missing_packages or ("iptables", "ipset")
    _append_result(
        report,
        CheckResult(
            "warn",
            "iptables и ipset (бан сканеров, whitelist порта панели)",
            detail="; ".join(parts) or fw.operational_detail,
            hint_ru=apt_install_hint(hint_pkgs),
        ),
    )


def format_check_line(result: CheckResult) -> str:
    tag = result.status.upper()
    lines = [f"[{tag}] {result.title}"]
    if result.detail:
        lines.append(f"       {result.detail}")
    if result.hint_ru:
        lines.append(f"       Подсказка (Debian/Ubuntu): {result.hint_ru}")
    return "\n".join(lines)


def format_report(report: DiagnosticsReport) -> str:
    parts = [format_check_line(r) for r in report.results]
    if report.recommended_commands:
        parts.append("")
        parts.append("Рекомендуемые команды:")
        for cmd in report.recommended_commands:
            parts.append(f"  {cmd}")
    return "\n".join(parts)
