"""«Проверка работы»: доступ к панели по IP сервера и кнопка «Закрыть доступ по IP»."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import User, UserRole
from app.routers import site_diagnostics as site_diagnostics_router
from app.services import nginx_default_deny as ndd
from app.services import site_diagnostics as sd


@pytest.fixture(autouse=True)
def _no_real_subprocess(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(f"real subprocess call in test: {args!r}")

    monkeypatch.setattr(subprocess, "run", refuse)


def _proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _line(status: str, *, ports=None, installed=False, **extra) -> str:
    payload = {"status": status, "installed": installed, **extra, "ports": ports or []}
    return json.dumps(payload)


PORTS_NEEDED = [
    {"port": 80, "kind": "http", "action": "install"},
    {"port": 443, "kind": "https", "action": "install"},
]


@pytest.fixture
def script(tmp_path: Path) -> Path:
    path = tmp_path / "scripts" / "nginx-default-deny.sh"
    path.parent.mkdir(parents=True)
    path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return path


# ---------- service: запуск скрипта и разбор строки статуса ----------


def test_run_script_parses_status_line_and_passes_mode(script):
    calls = []

    def run_cmd(args, timeout):
        calls.append((args, timeout))
        return _proc(stdout="[nginx-setup] noise\n" + _line("needed", ports=PORTS_NEEDED) + "\n")

    result = ndd.run_default_deny_script(script, "--check", run_cmd=run_cmd)

    assert calls == [(["bash", str(script), "--check"], ndd.CHECK_TIMEOUT)]
    assert result.ok is True
    assert result.status == "needed"
    assert result.installed is False
    assert [p["port"] for p in result.ports] == [80, 443]


def test_run_script_apply_uses_longer_timeout_and_reports_changed(script):
    seen = {}

    def run_cmd(args, timeout):
        seen["timeout"] = timeout
        return _proc(stdout=_line("installed", installed=True, changed=True, ports=PORTS_NEEDED))

    result = ndd.run_default_deny_script(script, "--apply", run_cmd=run_cmd)

    assert seen["timeout"] == ndd.APPLY_TIMEOUT
    assert result.ok is True
    assert result.status == "installed"
    assert result.changed is True


def test_run_script_failure_with_status_line_keeps_status_and_message(script):
    def run_cmd(args, timeout):
        return _proc(
            stdout=_line("needed", changed=False, error="install_failed", ports=PORTS_NEEDED),
            stderr="[nginx-setup] ВНИМАНИЕ: Сервер по умолчанию не прошёл nginx -t — убран\n",
            returncode=1,
        )

    result = ndd.run_default_deny_script(script, "--apply", run_cmd=run_cmd)

    assert result.ok is False
    assert result.status == "needed"
    assert result.error == "install_failed"
    assert "не прошёл nginx -t" in result.message
    assert "[nginx-setup]" not in result.message


def test_run_script_not_root_without_status_line(script):
    def run_cmd(args, timeout):
        return _proc(stderr="[nginx-setup] ОШИБКА: Запустите от root: sudo x\n", returncode=1)

    result = ndd.run_default_deny_script(script, "--check", run_cmd=run_cmd)

    assert result.ok is False
    assert result.status is None
    assert "root" in result.message


def test_run_script_missing(tmp_path):
    result = ndd.run_default_deny_script(
        tmp_path / "nope.sh", "--check", run_cmd=lambda *a: pytest.fail("must not run")
    )

    assert result.ok is False
    assert result.status is None
    assert "не найден" in result.message


def test_run_script_timeout(script):
    def run_cmd(args, timeout):
        raise subprocess.TimeoutExpired(args, timeout)

    result = ndd.run_default_deny_script(script, "--check", run_cmd=run_cmd)

    assert result.ok is False
    assert result.status is None
    assert "10" in result.message


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"PUBLISH_MODE": "nginx_le"}, True),
        ({"PUBLISH_MODE": "nginx_selfsigned"}, True),
        ({"PUBLISH_MODE": "nginx_custom", "BEHIND_NGINX": "false"}, True),
        ({"PUBLISH_MODE": "direct_http", "BEHIND_NGINX": "true"}, False),
        ({"BEHIND_NGINX": "true"}, True),
        ({}, False),
    ],
)
def test_is_nginx_publish_mode(env, expected):
    assert ndd.is_nginx_publish_mode(env) is expected


# ---------- диагностика: проверка «Доступ к панели по IP сервера» ----------


def _ctx(script: Path) -> sd.DiagnosticsContext:
    return sd.DiagnosticsContext(install_dir=str(script.parents[1]))


def _ip_check(report: sd.DiagnosticsReport) -> sd.CheckResult:
    matches = [r for r in report.results if r.check_id == sd.IP_ACCESS_CHECK_ID]
    assert len(matches) == 1
    return matches[0]


def _run_check(script, env, run_cmd) -> sd.CheckResult:
    report = sd.DiagnosticsReport()
    sd._set_category(report, "nginx")
    sd._check_ip_access(_ctx(script), env, report, run_cmd)
    return _ip_check(report)


def _script_returns(stdout="", stderr="", returncode=0):
    calls = []

    def run_cmd(args, timeout):
        calls.append(args)
        return _proc(stdout=stdout, stderr=stderr, returncode=returncode)

    run_cmd.calls = calls
    return run_cmd


NGINX_ENV = {"PUBLISH_MODE": "nginx_le", "DOMAIN": "panel.example.com"}


def test_check_needed_is_warn_with_action(script):
    run_cmd = _script_returns(_line("needed", ports=PORTS_NEEDED))

    check = _run_check(script, NGINX_ENV, run_cmd)

    assert run_cmd.calls == [["bash", str(script), "--check"]]
    assert check.status == "warn"
    assert check.category == "nginx"
    assert check.action == {"id": "close_ip_access", "label": "Закрыть доступ по IP"}
    assert "80" in check.detail and "443" in check.detail
    assert "nginx-default-deny.sh --apply" in check.hint_ru


def test_check_outdated_is_warn_with_action(script):
    check = _run_check(script, NGINX_ENV, _script_returns(_line("outdated", installed=True, ports=PORTS_NEEDED)))

    assert check.status == "warn"
    assert check.action is not None


def test_check_installed_is_ok_without_action(script):
    check = _run_check(script, NGINX_ENV, _script_returns(_line("installed", installed=True, ports=PORTS_NEEDED)))

    assert check.status == "ok"
    assert check.action is None
    assert "отклоняются" in check.title + check.detail


def test_check_installed_mentions_skipped_port(script):
    ports = [
        {"port": 80, "kind": "http", "action": "install"},
        {"port": 443, "kind": "https", "action": "skip", "reason": "ip_server_name"},
    ]
    check = _run_check(script, NGINX_ENV, _script_returns(_line("installed", installed=True, ports=ports)))

    assert check.status == "ok"
    assert "443" in check.detail


def test_check_own_default_is_ok_with_note(script):
    ports = [{"port": 80, "kind": "http", "action": "skip", "reason": "existing_default_server"}]
    check = _run_check(script, NGINX_ENV, _script_returns(_line("own_default", ports=ports)))

    assert check.status == "ok"
    assert check.action is None
    assert "default_server" in check.detail


def test_check_not_applicable_foreign_first(script):
    ports = [{"port": 443, "kind": "https", "action": "skip", "reason": "foreign_first"}]
    check = _run_check(script, NGINX_ENV, _script_returns(_line("not_applicable", ports=ports)))

    assert check.status == "ok"
    assert check.action is None
    assert "другой сайт" in check.detail


def test_check_disabled_is_ok_without_action(script):
    check = _run_check(script, NGINX_ENV, _script_returns(_line("disabled")))

    assert check.status == "ok"
    assert check.action is None
    assert "NGINX_DEFAULT_DENY=0" in check.title + check.detail


def test_check_disabled_but_still_installed_is_warn_with_apply_hint(script):
    check = _run_check(script, NGINX_ENV, _script_returns(_line("disabled", installed=True)))

    assert check.status == "warn"
    assert check.action is None
    assert "nginx-default-deny.sh --apply" in check.hint_ru


def test_check_not_applicable_without_panel_vhost_suggests_firewall(script):
    check = _run_check(script, NGINX_ENV, _script_returns(_line("not_applicable")))

    assert check.status == "ok"
    assert check.action is None
    assert "Защита входа" in check.hint_ru


def test_check_skipped_for_direct_publish_without_running_script(script):
    run_cmd = _script_returns()

    check = _run_check(script, {"PUBLISH_MODE": "direct_https"}, run_cmd)

    assert run_cmd.calls == []
    assert check.status == "ok"
    assert check.action is None
    assert "Защита входа" in check.hint_ru


def test_check_script_error_in_nginx_mode_is_warn_without_action(script):
    check = _run_check(
        script, NGINX_ENV, _script_returns(stderr="[nginx-setup] ОШИБКА: nginx не установлен\n", returncode=1)
    )

    assert check.status == "warn"
    assert check.action is None
    assert "не удалось" in check.title
    assert "nginx не установлен" in check.detail
    assert "nginx-default-deny.sh --check" in check.hint_ru


def test_check_script_missing_in_nginx_mode_is_warn(tmp_path):
    report = sd.DiagnosticsReport()
    sd._check_ip_access(sd.DiagnosticsContext(install_dir=str(tmp_path)), NGINX_ENV, report, _script_returns())

    check = _ip_check(report)
    assert check.status == "warn"
    assert check.action is None
    assert "не найден" in check.detail


def test_check_timeout_in_nginx_mode_is_warn(script):
    def run_cmd(args, timeout):
        raise subprocess.TimeoutExpired(args, timeout)

    check = _run_check(script, NGINX_ENV, run_cmd)

    assert check.status == "warn"
    assert check.action is None
    assert "не ответил" in check.detail


PORTS_NO_CERT = [
    {"port": 80, "kind": "http", "action": "install"},
    {"port": 443, "kind": "https", "action": "skip", "reason": "no_cert"},
]


def test_check_installed_http_only_without_cert_is_warn_without_action(script):
    check = _run_check(script, NGINX_ENV, _script_returns(_line("installed", installed=True, ports=PORTS_NO_CERT)))

    assert check.status == "warn"
    assert check.action is None
    assert "HTTP" in check.title
    assert "1.19.4" in check.detail and "443" in check.detail
    assert "nginx-default-deny.sh --apply" in check.hint_ru


def test_check_needed_mentions_no_cert_port(script):
    check = _run_check(script, NGINX_ENV, _script_returns(_line("needed", ports=PORTS_NO_CERT)))

    assert check.status == "warn"
    assert check.action is not None
    assert "сертификата-заглушки" in check.detail


def test_report_dict_exposes_id_and_action(script):
    report = sd.DiagnosticsReport()
    sd._set_category(report, "nginx")
    sd._check_ip_access(_ctx(script), NGINX_ENV, report, _script_returns(_line("needed", ports=PORTS_NEEDED)))

    data = sd.report_to_dict(report, _ctx(script))
    nginx_step = next(step for step in data["steps"] if step["id"] == "nginx")
    check = nginx_step["checks"][0]

    assert check["id"] == "ip_access"
    assert check["action"] == {"id": "close_ip_access", "label": "Закрыть доступ по IP"}
    plain = sd.report_to_dict(sd.DiagnosticsReport(results=[sd.CheckResult("ok", "x")]), _ctx(script))
    assert "action" not in plain["results"][0] and "id" not in plain["results"][0]


# ---------- API: POST /api/site-diagnostics/close-ip-access ----------


def _admin():
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "admin"
    user.role = UserRole.admin
    return user


@pytest.fixture
def api(script, monkeypatch):
    app = FastAPI()
    app.include_router(site_diagnostics_router.router, prefix="/api")
    app.dependency_overrides[require_admin] = _admin
    app.dependency_overrides[get_db] = lambda: MagicMock()

    env = dict(NGINX_ENV)
    runs: list[str] = []
    replies: dict[str, ndd.DefaultDenyResult] = {}
    logged: list[dict] = []

    monkeypatch.setattr(site_diagnostics_router, "resolve_diagnostics_context", lambda: _ctx(script))
    monkeypatch.setattr(site_diagnostics_router, "read_diagnostics_env", lambda ctx: env)

    def fake_run(path, mode, *, run_cmd=None):
        assert Path(path) == script
        runs.append(mode)
        return replies[mode]

    monkeypatch.setattr(site_diagnostics_router, "run_default_deny_script", fake_run)
    monkeypatch.setattr(site_diagnostics_router, "log_action", lambda db, **kw: logged.append(kw))

    active_tasks: dict[str, object] = {}
    monkeypatch.setattr(
        site_diagnostics_router.background_task_service,
        "find_active_task",
        lambda task_type: active_tasks.get(task_type),
    )

    with TestClient(app, base_url=f"https://{NGINX_ENV['DOMAIN']}") as client:
        yield {
            "client": client,
            "env": env,
            "runs": runs,
            "replies": replies,
            "logged": logged,
            "app": app,
            "active_tasks": active_tasks,
        }


def _result(status, *, ok=True, changed=False, installed=None, error="", message="", ports=None):
    return ndd.DefaultDenyResult(
        ok=ok,
        status=status,
        installed=status in ("installed", "outdated") if installed is None else installed,
        changed=changed,
        error=error,
        message=message,
        ports=PORTS_NEEDED if ports is None else ports,
    )


URL = "/api/site-diagnostics/close-ip-access"


def test_close_ip_access_applies_and_returns_new_check(api):
    api["replies"]["--check"] = _result("needed")
    api["replies"]["--apply"] = _result("installed", changed=True)

    resp = api["client"].post(URL)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert api["runs"] == ["--check", "--apply"]
    assert body["success"] is True
    assert body["status"] == "installed"
    assert body["changed"] is True
    assert body["message"]
    assert body["check"]["id"] == "ip_access"
    assert body["check"]["status"] == "ok"
    assert body["check"]["category"] == "nginx"
    assert len(api["logged"]) == 1
    entry = api["logged"][0]
    assert entry["action"] == "site_diagnostics_close_ip_access"
    assert entry["username"] == "admin"
    assert "status=installed" in entry["details"] and "changed=true" in entry["details"]


def test_close_ip_access_requires_admin(api):
    app = api["app"]
    app.dependency_overrides.pop(require_admin)
    viewer = MagicMock(spec=User)
    viewer.role = UserRole.user
    app.dependency_overrides[get_current_user] = lambda: viewer

    resp = api["client"].post(URL)

    assert resp.status_code == 403
    assert api["runs"] == []


def test_close_ip_access_refuses_direct_publish(api):
    api["env"].clear()
    api["env"]["PUBLISH_MODE"] = "direct_https"

    resp = api["client"].post(URL)

    assert resp.status_code == 409
    assert "nginx" in resp.json()["detail"]
    assert api["runs"] == []
    assert api["logged"] == []


def test_close_ip_access_refuses_when_disabled_by_env_flag(api):
    api["replies"]["--check"] = _result("disabled", ports=[])

    resp = api["client"].post(URL)

    assert resp.status_code == 409
    assert "NGINX_DEFAULT_DENY" in resp.json()["detail"]
    assert api["runs"] == ["--check"]
    assert api["logged"] == []


@pytest.mark.parametrize("status", ["not_applicable", "own_default"])
def test_close_ip_access_refuses_when_nothing_to_close(api, status):
    api["replies"]["--check"] = _result(status, ports=[])

    resp = api["client"].post(URL)

    assert resp.status_code == 409
    assert resp.json()["detail"]
    assert api["runs"] == ["--check"]
    assert api["logged"] == []


def test_close_ip_access_check_error_is_reported(api):
    api["replies"]["--check"] = _result(None, ok=False, message="Запустите от root")

    resp = api["client"].post(URL)

    assert resp.status_code == 500
    assert "root" in resp.json()["detail"]
    assert api["runs"] == ["--check"]


def test_close_ip_access_apply_failure_is_logged_and_reported(api):
    api["replies"]["--check"] = _result("needed")
    api["replies"]["--apply"] = _result(
        "needed", ok=False, error="install_failed", message="Сервер по умолчанию не прошёл nginx -t — убран"
    )

    resp = api["client"].post(URL)

    assert resp.status_code == 500
    assert "nginx -t" in resp.json()["detail"]
    assert len(api["logged"]) == 1
    assert "status=failed" in api["logged"][0]["details"]
    assert "install_failed" in api["logged"][0]["details"]


@pytest.mark.parametrize("task_type", ["vpn_network_publish", "portal_publish", "portal_readiness_prepare"])
def test_close_ip_access_conflicts_with_active_nginx_task(api, task_type):
    task = MagicMock()
    task.id = "task-42"
    api["active_tasks"][task_type] = task

    resp = api["client"].post(URL)

    assert resp.status_code == 409
    body = resp.json()
    assert body["active_task_id"] == "task-42"
    assert body["detail"]
    assert api["runs"] == []
    assert api["logged"] == []


def test_close_ip_access_ignores_unrelated_active_task(api):
    api["active_tasks"]["run_doall"] = MagicMock(id="other")
    api["replies"]["--check"] = _result("needed")
    api["replies"]["--apply"] = _result("installed", changed=True)

    resp = api["client"].post(URL)

    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize(
    ("status", "changed", "expected", "unexpected"),
    [
        ("installed", True, "закрыт — nginx перечитал", "уже"),
        ("installed", False, "уже был закрыт", "перечитал"),
        ("not_applicable", True, "Устаревший сервер по умолчанию убран", "закрыт"),
        ("own_default", False, "нечего", "закрыт"),
    ],
)
def test_close_ip_access_message_follows_result_status(api, status, changed, expected, unexpected):
    api["replies"]["--check"] = _result("outdated")
    api["replies"]["--apply"] = _result(status, changed=changed, ports=[] if status != "installed" else None)

    resp = api["client"].post(URL)

    assert resp.status_code == 200, resp.text
    message = resp.json()["message"]
    assert expected in message
    assert unexpected not in message


@pytest.mark.parametrize(
    "host",
    ["203.0.113.10", "203.0.113.10:8443", "[2001:db8::1]:443", "other.example.com", "www.panel.example.com"],
)
def test_close_ip_access_refuses_when_panel_opened_not_by_domain(api, host):
    api["replies"]["--check"] = _result("needed")
    api["replies"]["--apply"] = _result("installed", changed=True)

    resp = api["client"].post(URL, headers={"Host": host})

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "https://panel.example.com/" in detail
    assert "потеряете доступ" in detail
    assert api["runs"] == []
    assert api["logged"] == []


def test_close_ip_access_refusal_links_panel_with_port_and_path(api):
    api["env"].update({"HTTPS_PUBLIC_PORT": "8443", "ACCESS_PATH": "/panel"})

    resp = api["client"].post(URL, headers={"Host": "203.0.113.10:8443"})

    assert resp.status_code == 409
    assert "https://panel.example.com:8443/panel/" in resp.json()["detail"]


@pytest.mark.parametrize("host", ["PANEL.example.com", "panel.example.com:8443", "panel.example.com.", "localhost:8000"])
def test_close_ip_access_allows_domain_and_local_hosts(api, host):
    api["replies"]["--check"] = _result("needed")
    api["replies"]["--apply"] = _result("installed", changed=True)

    resp = api["client"].post(URL, headers={"Host": host})

    assert resp.status_code == 200, resp.text
    assert api["runs"] == ["--check", "--apply"]


def test_close_ip_access_refuses_behind_another_reverse_proxy(api):
    api["replies"]["--check"] = _result("needed")
    api["replies"]["--apply"] = _result("installed", changed=True)

    resp = api["client"].post(URL, headers={"X-Forwarded-For": "198.51.100.7, 192.168.1.10"})

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "proxy_ssl_server_name on" in detail
    assert "nginx-default-deny.sh --apply" in detail
    assert api["runs"] == []


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Forwarded-For": "198.51.100.7"},
        {"X-Forwarded-For": "198.51.100.7, 172.70.1.1", "CF-Connecting-IP": "198.51.100.7"},
    ],
)
def test_close_ip_access_allows_direct_client_and_cloudflare(api, headers):
    api["replies"]["--check"] = _result("needed")
    api["replies"]["--apply"] = _result("installed", changed=True)

    resp = api["client"].post(URL, headers=headers)

    assert resp.status_code == 200, resp.text


def test_close_ip_access_refuses_without_domain(api):
    api["env"]["DOMAIN"] = ""

    resp = api["client"].post(URL)

    assert resp.status_code == 409
    assert "DOMAIN" in resp.json()["detail"]
    assert api["runs"] == []


def test_close_ip_access_http_only_message_mentions_https(api):
    api["replies"]["--check"] = _result("needed")
    api["replies"]["--apply"] = _result("installed", changed=True, ports=PORTS_NO_CERT)

    resp = api["client"].post(URL)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "HTTPS по IP остался открыт" in body["message"]
    assert body["check"]["status"] == "warn"
    assert "action" not in body["check"]
