"""Collect AdminPanelAZ process metrics on the controller machine."""

from __future__ import annotations

import os
import platform
import time
from datetime import datetime, timezone
from typing import Any

import psutil

from app.config import get_settings

settings = get_settings()

_CPU_READY = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ensure_cpu() -> None:
    global _CPU_READY
    if not _CPU_READY:
        psutil.cpu_percent(interval=None)
        _CPU_READY = True


def _safe_cmdline(proc: psutil.Process) -> str:
    try:
        return " ".join(proc.cmdline()).lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""


def _match_backend(cmd: str) -> bool:
    if not cmd:
        return False
    if "uvicorn" in cmd and "app.main" in cmd:
        return True
    if "adminpanelaz" in cmd and ("uvicorn" in cmd or "app.main" in cmd):
        return True
    return False


def _match_watchdog(cmd: str) -> bool:
    if not cmd:
        return False
    if "start.sh" in cmd:
        return True
    return "watchdog" in cmd and "adminpanelaz" in cmd


def _match_nginx(cmd: str) -> bool:
    return bool(cmd) and "nginx" in cmd


def _match_frontend_dev(cmd: str) -> bool:
    if not cmd:
        return False
    panel_hint = "adminpanelaz" in cmd.replace("\\", "/")
    if not panel_hint and "vite" not in cmd and "npm" not in cmd:
        return False
    return "vite" in cmd or "npm run dev" in cmd


def _proc_stats(procs: list[psutil.Process]) -> dict[str, Any]:
    cpu = 0.0
    rss = 0
    for proc in procs:
        try:
            cpu += proc.cpu_percent(interval=None) or 0.0
            rss += proc.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    memory_mb = rss // (1024 * 1024)
    return {
        "cpu_percent": round(cpu, 1),
        "memory_mb": memory_mb,
        "rss_mb": memory_mb,
        "process_count": len(procs),
    }


def _scan_panel_processes() -> tuple[list[psutil.Process], list[psutil.Process], list[psutil.Process], list[psutil.Process]]:
    backend: list[psutil.Process] = []
    watchdog: list[psutil.Process] = []
    nginx: list[psutil.Process] = []
    frontend_dev: list[psutil.Process] = []
    seen: set[int] = set()

    candidates: list[psutil.Process] = []
    try:
        candidates.append(psutil.Process(os.getpid()))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    for proc in psutil.process_iter():
        try:
            if proc.pid in seen:
                continue
            cmd = _safe_cmdline(proc)
            if not cmd:
                continue
            if _match_backend(cmd):
                backend.append(proc)
                seen.add(proc.pid)
            elif _match_watchdog(cmd):
                watchdog.append(proc)
                seen.add(proc.pid)
            elif settings.behind_nginx and _match_nginx(cmd):
                nginx.append(proc)
                seen.add(proc.pid)
            elif _match_frontend_dev(cmd):
                frontend_dev.append(proc)
                seen.add(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    for proc in candidates:
        if proc.pid not in seen and _match_backend(_safe_cmdline(proc)):
            backend.append(proc)
            seen.add(proc.pid)

    return backend, watchdog, nginx, frontend_dev


def _collect_host_metrics() -> dict[str, Any]:
    cpu = psutil.cpu_percent(interval=None) or 0.0
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load_1: float | None = None
    try:
        la = os.getloadavg() if hasattr(os, "getloadavg") else psutil.getloadavg()
        load_1 = round(la[0], 2)
    except (OSError, AttributeError):
        pass
    boot = psutil.boot_time()
    uptime_s = time.time() - boot
    days, rem = divmod(uptime_s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    return {
        "host_cpu_percent": round(cpu, 1),
        "host_memory_percent": round(mem.percent, 1),
        "host_memory_used_mb": mem.used // (1024 * 1024),
        "host_memory_total_mb": mem.total // (1024 * 1024),
        "host_disk_percent": round(disk.percent, 1),
        "host_load_1": load_1,
        "host_hostname": platform.node(),
        "host_uptime": f"{int(days)}д {int(hours)}ч {int(minutes)}м",
    }


def collect_panel_metrics() -> dict[str, Any]:
    """Live snapshot of panel-related processes on this machine."""
    _ensure_cpu()
    backend_procs, watchdog_procs, nginx_procs, frontend_dev_procs = _scan_panel_processes()

    backend = _proc_stats(backend_procs)
    watchdog = _proc_stats(watchdog_procs) if watchdog_procs else None
    nginx = _proc_stats(nginx_procs) if nginx_procs else None
    frontend_dev = _proc_stats(frontend_dev_procs) if frontend_dev_procs else None

    total_memory_mb = backend["memory_mb"]
    if watchdog:
        total_memory_mb += watchdog["memory_mb"]
    if nginx:
        total_memory_mb += nginx["memory_mb"]
    if frontend_dev:
        total_memory_mb += frontend_dev["memory_mb"]

    workers = sum(1 for p in backend_procs if "app.main" in _safe_cmdline(p))
    if workers == 0:
        workers = backend["process_count"]

    return {
        "timestamp": _utcnow(),
        "backend_cpu_percent": backend["cpu_percent"],
        "backend_memory_mb": backend["memory_mb"],
        "backend_rss_mb": backend["rss_mb"],
        "backend_workers": workers,
        "nginx_memory_mb": nginx["memory_mb"] if nginx else None,
        "watchdog_memory_mb": watchdog["memory_mb"] if watchdog else None,
        "frontend_dev_memory_mb": frontend_dev["memory_mb"] if frontend_dev else None,
        "total_panel_memory_mb": total_memory_mb,
        "frontend_note": (
            "Статические файлы раздаёт backend (FastAPI)"
            if settings.serve_frontend
            else "Frontend dev-сервер (Vite) — только в режиме разработки"
            if frontend_dev
            else "Статические файлы раздаёт backend (FastAPI)"
        ),
        **_collect_host_metrics(),
    }
