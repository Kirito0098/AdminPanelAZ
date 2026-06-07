"""Server resource monitoring (ported from AdminAntizapret server_monitor)."""

import os
import platform
import subprocess
import time
from datetime import datetime, timezone

import psutil


class ServerMonitorService:
    def __init__(self):
        self._cpu_ready = False

    def _ensure_cpu(self):
        if not self._cpu_ready:
            psutil.cpu_percent(interval=None)
            self._cpu_ready = True

    def get_metrics(self, *, accurate_cpu: bool = False) -> dict:
        self._ensure_cpu()
        cpu = psutil.cpu_percent(interval=1 if accurate_cpu else None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        boot = psutil.boot_time()
        uptime_s = time.time() - boot
        days, rem = divmod(uptime_s, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        load = {}
        try:
            la = os.getloadavg() if hasattr(os, "getloadavg") else psutil.getloadavg()
            load = {"load_1m": round(la[0], 2), "load_5m": round(la[1], 2), "load_15m": round(la[2], 2)}
        except (OSError, AttributeError):
            pass
        return {
            "cpu_percent": round(cpu, 1),
            "memory_percent": round(mem.percent, 1),
            "memory_used": mem.used,
            "memory_total": mem.total,
            "disk_percent": round(disk.percent, 1),
            "disk_used": disk.used,
            "disk_total": disk.total,
            "uptime": f"{int(days)}д {int(hours)}ч {int(minutes)}м",
            "load_average": load,
            "cpu_count": psutil.cpu_count(),
            "hostname": platform.node(),
            "os": platform.system(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_bandwidth(self, iface: str = "eth0", range_key: str = "1d") -> dict:
        try:
            result = subprocess.run(
                ["vnstat", "-i", iface, "--json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "vnstat недоступен", "iface": iface}
            import json
            data = json.loads(result.stdout)
            return {"iface": iface, "range": range_key, "data": data}
        except FileNotFoundError:
            return {"error": "vnstat не установлен", "iface": iface}
        except Exception as exc:
            return {"error": str(exc), "iface": iface}

    def list_interfaces(self) -> list[str]:
        try:
            result = subprocess.run(["vnstat", "--iflist"], capture_output=True, text=True, timeout=5, check=False)
            if result.returncode != 0:
                return ["eth0", "ens3"]
            return [i.strip() for i in result.stdout.split() if i.strip()] or ["eth0"]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return list(psutil.net_if_stats().keys())[:5] or ["eth0"]
