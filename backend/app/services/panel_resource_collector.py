"""Collect RAM for AdminPanelAZ + local node and services the node manages on this host."""

from __future__ import annotations

import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import psutil

from app.config import get_settings

settings = get_settings()

_CPU_READY = False
_EXCLUDED_PATH_MARKERS = ("/opt/adminantizapret",)
_MANAGED_VPN_PROCESS_NAMES = frozenset(
    {
        "openvpn",
        "dnsmasq",
        "stubby",
        "dnscrypt-proxy",
        "sing-box",
        "xray",
        "haproxy",
    }
)
StackRole = Literal["panel", "node_agent", "managed_vpn"]


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


def _safe_name(proc: psutil.Process) -> str:
    try:
        return (proc.name() or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""


def _safe_exe(proc: psutil.Process) -> str:
    try:
        return (proc.exe() or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""


def _safe_cwd(proc: psutil.Process) -> str:
    try:
        return (proc.cwd() or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
        return ""


def _normalize_path(text: str) -> str:
    return text.replace("\\", "/")


def _path_contains(text: str, hint: str) -> bool:
    return bool(hint) and hint in _normalize_path(text)


def _path_contains_any(text: str, hints: list[str]) -> bool:
    return any(_path_contains(text, hint) for hint in hints)


def _is_excluded_path(text: str) -> bool:
    normalized = _normalize_path(text)
    return any(marker in normalized for marker in _EXCLUDED_PATH_MARKERS)


def _repo_root_hints() -> list[str]:
    from app.services.node_update import resolve_repo_root

    hints: list[str] = []
    root = resolve_repo_root()
    if root is not None:
        try:
            hints.append(str(root.resolve()).lower())
        except OSError:
            hints.append(str(root).lower())
    return hints


def _antizapret_path_hints() -> list[str]:
    hints: list[str] = []
    for raw in (settings.antizapret_path, Path("/root/antizapret")):
        try:
            text = str(raw.resolve()).lower()
        except OSError:
            text = str(raw).lower()
        if text and text not in hints:
            hints.append(text)
    return hints


def _classify_stack_process(name: str, blob: str, cwd: str) -> StackRole | None:
    """Classify process into AdminPanelAZ stack (panel / node agent / node-managed VPN)."""
    if _is_excluded_path(blob) or _is_excluded_path(cwd):
        return None

    repo_hints = _repo_root_hints()
    az_hints = _antizapret_path_hints()

    if "start_node_agent" in blob or "node_agent/main" in blob or "node_agent.main" in blob:
        return "node_agent"
    if "node_agent" in blob and _path_contains_any(blob, repo_hints):
        return "node_agent"
    if "uvicorn" in blob and "node_agent" in blob:
        return "node_agent"

    if _path_contains_any(blob, repo_hints):
        if "uvicorn" in blob and "app.main" in blob:
            return "panel"
        if "start.sh" in blob and "start_node_agent" not in blob:
            return "panel"
        if "watchdog" in blob and "adminpanelaz" in blob:
            return "panel"
        if "vite" in blob or "npm run dev" in blob:
            return "panel"

    if settings.behind_nginx and "nginx" in blob and _path_contains_any(blob, repo_hints):
        return "panel"

    if not settings.local_antizapret_enabled:
        return None

    if name in _MANAGED_VPN_PROCESS_NAMES or name.startswith("openvpn"):
        return "managed_vpn"
    if "wireguard" in blob or "wg-quick" in blob or blob.strip().startswith("wg "):
        return "managed_vpn"
    if _path_contains_any(blob, az_hints) or _path_contains_any(cwd, az_hints):
        return "managed_vpn"

    return None


def _scan_stack_processes() -> dict[StackRole, list[psutil.Process]]:
    stacks: dict[StackRole, list[psutil.Process]] = {
        "panel": [],
        "node_agent": [],
        "managed_vpn": [],
    }
    seen: set[int] = set()

    for proc in psutil.process_iter():
        try:
            if proc.pid in seen:
                continue
            cmd = _safe_cmdline(proc)
            name = _safe_name(proc)
            exe = _safe_exe(proc)
            cwd = _safe_cwd(proc)
            blob = f"{cmd} {exe} {cwd}"
            role = _classify_stack_process(name, blob, cwd)
            if role is None:
                continue
            stacks[role].append(proc)
            seen.add(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    current_pid = os.getpid()
    if current_pid not in seen:
        try:
            proc = psutil.Process(current_pid)
            role = _classify_stack_process(_safe_name(proc), f"{_safe_cmdline(proc)} {_safe_exe(proc)}", _safe_cwd(proc))
            if role == "panel":
                stacks["panel"].append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return stacks


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


def _split_panel_stats(
    panel_procs: list[psutil.Process],
) -> tuple[dict[str, Any], int, int | None, int | None, int | None]:
    backend: list[psutil.Process] = []
    watchdog: list[psutil.Process] = []
    nginx: list[psutil.Process] = []
    frontend_dev: list[psutil.Process] = []

    for proc in panel_procs:
        cmd = _safe_cmdline(proc)
        if _match_backend(cmd):
            backend.append(proc)
        elif _match_watchdog(cmd):
            watchdog.append(proc)
        elif settings.behind_nginx and _match_nginx(cmd):
            nginx.append(proc)
        elif _match_frontend_dev(cmd):
            frontend_dev.append(proc)
        else:
            backend.append(proc)

    backend_stats = _proc_stats(backend)
    watchdog_stats = _proc_stats(watchdog) if watchdog else None
    nginx_stats = _proc_stats(nginx) if nginx else None
    frontend_stats = _proc_stats(frontend_dev) if frontend_dev else None

    workers = sum(1 for p in backend if "app.main" in _safe_cmdline(p))
    if workers == 0:
        workers = backend_stats["process_count"]

    return (
        backend_stats,
        workers,
        watchdog_stats["memory_mb"] if watchdog_stats else None,
        nginx_stats["memory_mb"] if nginx_stats else None,
        frontend_stats["memory_mb"] if frontend_stats else None,
    )


def _match_backend(cmd: str) -> bool:
    return bool(cmd) and "uvicorn" in cmd and "app.main" in cmd


def _match_watchdog(cmd: str) -> bool:
    return bool(cmd) and "start.sh" in cmd and "start_node_agent" not in cmd


def _match_nginx(cmd: str) -> bool:
    return bool(cmd) and "nginx" in cmd


def _match_frontend_dev(cmd: str) -> bool:
    if not cmd:
        return False
    return "vite" in cmd or "npm run dev" in cmd


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
    """RAM snapshot: AdminPanelAZ + local node agent + VPN services under ANTIZAPRET_PATH."""
    _ensure_cpu()
    stacks = _scan_stack_processes()

    panel_stats = _proc_stats(stacks["panel"])
    node_agent_stats = _proc_stats(stacks["node_agent"])
    managed_vpn_stats = _proc_stats(stacks["managed_vpn"])

    backend_stats, workers, watchdog_mb, nginx_mb, frontend_dev_mb = _split_panel_stats(stacks["panel"])

    total_panel_memory_mb = panel_stats["memory_mb"]
    node_agent_memory_mb = node_agent_stats["memory_mb"]
    managed_vpn_memory_mb = managed_vpn_stats["memory_mb"]
    local_node_memory_mb = node_agent_memory_mb + managed_vpn_memory_mb
    total_stack_memory_mb = total_panel_memory_mb + local_node_memory_mb

    return {
        "timestamp": _utcnow(),
        "backend_cpu_percent": backend_stats["cpu_percent"],
        "backend_memory_mb": backend_stats["memory_mb"],
        "backend_rss_mb": backend_stats["rss_mb"],
        "backend_workers": workers,
        "nginx_memory_mb": nginx_mb,
        "watchdog_memory_mb": watchdog_mb,
        "frontend_dev_memory_mb": frontend_dev_mb,
        "total_panel_memory_mb": total_panel_memory_mb,
        "node_agent_memory_mb": node_agent_memory_mb,
        "managed_vpn_memory_mb": managed_vpn_memory_mb,
        "local_vpn_core_memory_mb": managed_vpn_memory_mb,
        "legacy_antizapret_memory_mb": 0,
        "local_node_memory_mb": local_node_memory_mb,
        "total_stack_memory_mb": total_stack_memory_mb,
        "local_node_on_host": bool(settings.local_antizapret_enabled),
        "stack_note": "",
        "frontend_note": (
            "Статические файлы раздаёт backend (FastAPI)"
            if settings.serve_frontend
            else "Frontend dev-сервер (Vite) — только в режиме разработки"
            if frontend_dev_mb
            else "Статические файлы раздаёт backend (FastAPI)"
        ),
        **_collect_host_metrics(),
    }
