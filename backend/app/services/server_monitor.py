"""Server resource monitoring (ported from AdminAntizapret server_monitor)."""

import json
import os
import platform
import re
import subprocess
import time
from datetime import datetime, timezone

import psutil


def vnstat_bin() -> str:
    return os.environ.get("VNSTAT_BIN", "vnstat")


def is_vnstat_available() -> bool:
    try:
        proc = subprocess.run(
            [vnstat_bin(), "--json"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        return proc.returncode == 0
    except FileNotFoundError:
        return False
    except Exception:
        return False


def collect_interface_groups() -> dict[str, list[str]]:
    default_groups = {
        "vpn": ["vpn", "vpn-udp", "vpn-tcp"],
        "antizapret": ["antizapret", "antizapret-udp", "antizapret-tcp"],
    }
    candidates: set[str] = set()
    for values in default_groups.values():
        candidates.update(values)
    vnstat = vnstat_bin()
    try:
        vn_json = subprocess.run([vnstat, "--json"], capture_output=True, text=True, timeout=4, check=False)
        if vn_json.returncode == 0:
            parsed = json.loads(vn_json.stdout or "{}")
            for item in parsed.get("interfaces") or []:
                name = str(item.get("name") or "").strip()
                if name:
                    candidates.add(name)
    except Exception:
        pass
    wg_interfaces: set[str] = set()
    try:
        wg_out = subprocess.run(["wg", "show", "interfaces"], capture_output=True, text=True, timeout=3, check=False)
        for token in re.split(r"\s+", (wg_out.stdout or "").strip()):
            if token.strip():
                wg_interfaces.add(token.strip())
                candidates.add(token.strip())
    except Exception:
        pass
    vpn_group: list[str] = []
    antizapret_group: list[str] = []
    openvpn_group: list[str] = []
    wireguard_group: list[str] = []

    def _add_unique(target: list[str], value: str) -> None:
        if value and value not in target:
            target.append(value)

    for iface in sorted(candidates):
        lowered = iface.lower()
        if not any(k in lowered for k in ("vpn", "wg", "wireguard", "awg", "amnezia", "antizapret")):
            continue
        is_wg = iface in wg_interfaces or any(k in lowered for k in ("wg", "wireguard", "awg", "amnezia"))
        if "antizapret" in lowered:
            _add_unique(antizapret_group, iface)
        else:
            _add_unique(vpn_group, iface)
        if is_wg:
            _add_unique(wireguard_group, iface)
        else:
            _add_unique(openvpn_group, iface)
    for fallback in default_groups["vpn"]:
        _add_unique(vpn_group, fallback)
    for fallback in default_groups["antizapret"]:
        _add_unique(antizapret_group, fallback)
    return {
        "vpn": vpn_group,
        "antizapret": antizapret_group,
        "openvpn": openvpn_group,
        "wireguard": wireguard_group,
    }


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
        iface = (iface or "").strip() or "eth0"
        rng = range_key if range_key in ("1d", "7d", "30d") else "1d"
        vnstat = vnstat_bin()

        def _run(args: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)

        if not is_vnstat_available():
            return {
                "error": "vnstat не установлен на этом узле. Установите: apt install -y vnstat && sudo ./scripts/setup-vnstat.sh",
                "iface": iface,
            }

        try:
            data_f = json.loads(_run([vnstat, "--json", "f", "-i", iface]).stdout or "{}")
        except Exception:
            data_f = {}
        try:
            proc_d = _run([vnstat, "--json", "d", "-i", iface])
            if proc_d.returncode != 0:
                return {"error": proc_d.stderr.strip() or "vnstat недоступен", "iface": iface}
            data_d = json.loads(proc_d.stdout or "{}")
        except FileNotFoundError:
            return {
                "error": "vnstat не установлен на этом узле. Установите: apt install -y vnstat && sudo ./scripts/setup-vnstat.sh",
                "iface": iface,
            }
        except Exception as exc:
            return {"error": str(exc), "iface": iface}

        def get_iface_block(data: dict) -> dict:
            for it in data.get("interfaces") or []:
                if it.get("name") == iface:
                    return it
            return {}

        it_f = get_iface_block(data_f)
        it_d = get_iface_block(data_d)
        traffic_f = it_f.get("traffic") or {}
        traffic_d = it_d.get("traffic") or {}
        fivemin = (
            traffic_f.get("fiveminute")
            or traffic_f.get("fiveMinute")
            or traffic_f.get("five_minutes")
            or []
        )
        days = traffic_d.get("day") or traffic_d.get("days") or []

        def sort_key_dt(h: dict) -> tuple:
            d = h.get("date") or {}
            t = h.get("time") or {}
            return (
                d.get("year", 0),
                d.get("month", 0),
                d.get("day", 0),
                t.get("hour", 0) if t else 0,
                t.get("minute", 0) if t else 0,
            )

        def to_mbps_from_5min_bytes(b: int) -> float:
            return round((int(b) * 8) / (300 * 1_000_000), 3)

        def to_mbps_avg_per_day(bytes_val: int) -> float:
            return round((int(bytes_val) * 8) / (86_400 * 1_000_000), 3)

        labels: list[str] = []
        rx_mbps: list[float] = []
        tx_mbps: list[float] = []

        if rng == "1d":
            if fivemin:
                last288 = sorted(fivemin, key=sort_key_dt)[-288:]
                for m in last288:
                    t = m.get("time") or {}
                    labels.append(f"{int(t.get('hour', 0)):02d}:{int(t.get('minute', 0)):02d}")
                    rx_mbps.append(to_mbps_from_5min_bytes(m.get("rx", 0)))
                    tx_mbps.append(to_mbps_from_5min_bytes(m.get("tx", 0)))
            else:
                labels, rx_mbps, tx_mbps = [""] * 288, [0.0] * 288, [0.0] * 288
        else:
            need_days = 7 if rng == "7d" else 30
            use_days = sorted(days, key=sort_key_dt)[-need_days:]
            for d in use_days:
                date = d.get("date") or {}
                labels.append(f"{int(date.get('day', 0)):02d}.{int(date.get('month', 0)):02d}")
                rx_mbps.append(to_mbps_avg_per_day(d.get("rx", 0)))
                tx_mbps.append(to_mbps_avg_per_day(d.get("tx", 0)))
            if len(labels) < need_days:
                pad = need_days - len(labels)
                labels = [""] * pad + labels
                rx_mbps = [0.0] * pad + rx_mbps
                tx_mbps = [0.0] * pad + tx_mbps

        days_sorted = sorted(days, key=sort_key_dt)

        def sum_days(n: int) -> dict:
            chunk = days_sorted[-n:] if days_sorted else []
            rx_sum = sum(int(x.get("rx", 0)) for x in chunk)
            tx_sum = sum(int(x.get("tx", 0)) for x in chunk)
            return {"rx_bytes": rx_sum, "tx_bytes": tx_sum, "total_bytes": rx_sum + tx_sum}

        return {
            "iface": iface,
            "range": rng,
            "labels": labels,
            "rx_mbps": rx_mbps,
            "tx_mbps": tx_mbps,
            "totals": {"1d": sum_days(1), "7d": sum_days(7), "30d": sum_days(30)},
        }

    def list_interfaces(self) -> dict:
        groups = collect_interface_groups()
        all_ifaces: list[str] = []
        for group in groups.values():
            for iface in group:
                if iface not in all_ifaces:
                    all_ifaces.append(iface)
        if not all_ifaces:
            all_ifaces = list(psutil.net_if_stats().keys())[:5] or ["eth0"]
        return {"interfaces": all_ifaces, "groups": groups, "vnstat_available": is_vnstat_available()}
