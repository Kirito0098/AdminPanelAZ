"""Server resource monitoring (ported from AdminAntizapret server_monitor)."""

import json
import os
import platform
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psutil

# Cheap probes: cache availability / interface discovery across WS + REST ticks.
_VNSTAT_AVAIL_TTL_S = 60.0
_IFACE_LIST_TTL_S = 30.0

_vnstat_avail_cache: tuple[float, bool] | None = None
_iface_list_cache: tuple[float, dict] | None = None


def vnstat_bin() -> str:
    return os.environ.get("VNSTAT_BIN", "vnstat")


def clear_server_monitor_caches() -> None:
    """Test helper — drop TTL caches for vnstat / interface discovery."""
    global _vnstat_avail_cache, _iface_list_cache
    _vnstat_avail_cache = None
    _iface_list_cache = None


def _format_utc_offset(dt: datetime) -> str:
    offset = dt.utcoffset()
    if offset is None:
        return "UTC"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    if minutes:
        return f"UTC{sign}{hours}:{minutes:02d}"
    return f"UTC{sign}{hours}"


def _node_timezone() -> tzinfo:
    tz_name = os.environ.get("TZ", "").strip()
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            pass
    current = datetime.now().astimezone()
    tzinfo = current.tzinfo
    if tzinfo is not None:
        return tzinfo
    return timezone.utc


def _node_timezone_name() -> str:
    tz_name = os.environ.get("TZ", "").strip()
    if tz_name:
        return tz_name
    current = datetime.now().astimezone()
    tzinfo = current.tzinfo
    if tzinfo is None:
        return "UTC"
    key = getattr(tzinfo, "key", None)
    if key:
        return str(key)
    name = current.tzname()
    if name:
        return name
    return _format_utc_offset(current)


def bandwidth_point_timestamp(date_dict: dict, time_dict: dict) -> str:
    tz = _node_timezone()
    local_dt = datetime(
        int(date_dict.get("year", 0) or 0),
        int(date_dict.get("month", 1) or 1),
        int(date_dict.get("day", 1) or 1),
        int(time_dict.get("hour", 0) or 0),
        int(time_dict.get("minute", 0) or 0),
        0,
        tzinfo=tz,
    )
    return local_dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_vnstat_available(*, force: bool = False) -> bool:
    """Return whether vnstat can be invoked. Cached; prefers --version over --json."""
    global _vnstat_avail_cache
    now = time.monotonic()
    if not force and _vnstat_avail_cache is not None:
        cached_at, cached_ok = _vnstat_avail_cache
        if now - cached_at < _VNSTAT_AVAIL_TTL_S:
            return cached_ok

    ok = False
    binary = vnstat_bin()
    try:
        resolved = shutil.which(binary)
        if resolved is None and not Path(binary).exists():
            ok = False
        else:
            proc = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            ok = proc.returncode == 0
    except FileNotFoundError:
        ok = False
    except Exception:
        ok = False

    _vnstat_avail_cache = (now, ok)
    return ok


def _net_if_stats() -> dict:
    try:
        return psutil.net_if_stats()
    except Exception:
        return {}


def interface_exists(name: str) -> bool:
    name = (name or "").strip()
    return bool(name) and name in _net_if_stats()


def detect_primary_interface() -> str | None:
    try:
        proc = subprocess.run(
            ["ip", "-4", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.split()
            if "dev" in parts:
                idx = parts.index("dev")
                if idx + 1 < len(parts):
                    candidate = parts[idx + 1].strip()
                    if interface_exists(candidate):
                        return candidate
    except Exception:
        pass
    stats = _net_if_stats()
    for candidate in ("eth0", "ens3", "enp0s3", "eno1", "enp0s8"):
        if candidate in stats:
            return candidate
    for name, st in stats.items():
        if name != "lo" and st.isup:
            return name
    return None


def collect_interface_groups() -> dict[str, list[str]]:
    default_groups = {
        "vpn": ["vpn", "vpn-udp", "vpn-tcp"],
        "antizapret": ["antizapret", "antizapret-udp", "antizapret-tcp"],
    }
    candidates: set[str] = set()
    for values in default_groups.values():
        candidates.update(values)
    vnstat = vnstat_bin()
    # Prefer cached availability; only run heavy --json when vnstat is known present.
    if is_vnstat_available():
        try:
            vn_json = subprocess.run(
                [vnstat, "--json"],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
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
        wg_out = subprocess.run(
            ["wg", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        for token in re.split(r"\s+", (wg_out.stdout or "").strip()):
            if token.strip():
                wg_interfaces.add(token.strip())
                candidates.add(token.strip())
    except Exception:
        pass
    primary = detect_primary_interface()
    main_group: list[str] = []
    vpn_group: list[str] = []
    antizapret_group: list[str] = []
    openvpn_group: list[str] = []
    wireguard_group: list[str] = []

    def _add_unique(target: list[str], value: str) -> None:
        if value and interface_exists(value) and value not in target:
            target.append(value)

    if primary:
        _add_unique(main_group, primary)

    for iface in sorted(candidates):
        if not interface_exists(iface):
            continue
        lowered = iface.lower()
        if not any(k in lowered for k in ("vpn", "wg", "wireguard", "awg", "amnezia", "antizapret")):
            continue
        is_openvpn = lowered.endswith("-udp") or lowered.endswith("-tcp")
        is_wg = not is_openvpn and (
            iface in wg_interfaces
            or lowered in ("vpn", "antizapret")
            or any(k in lowered for k in ("wg", "wireguard", "awg", "amnezia"))
        )
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
        "main": main_group,
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
            clear_server_monitor_caches()
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
        timestamps: list[str] = []
        rx_mbps: list[float] = []
        tx_mbps: list[float] = []

        if rng == "1d":
            if fivemin:
                last288 = sorted(fivemin, key=sort_key_dt)[-288:]
                for m in last288:
                    date = m.get("date") or {}
                    t = m.get("time") or {}
                    labels.append(f"{int(t.get('hour', 0)):02d}:{int(t.get('minute', 0)):02d}")
                    timestamps.append(bandwidth_point_timestamp(date, t))
                    rx_mbps.append(to_mbps_from_5min_bytes(m.get("rx", 0)))
                    tx_mbps.append(to_mbps_from_5min_bytes(m.get("tx", 0)))
            else:
                labels, timestamps, rx_mbps, tx_mbps = [""] * 288, [""] * 288, [0.0] * 288, [0.0] * 288
        else:
            need_days = 7 if rng == "7d" else 30
            use_days = sorted(days, key=sort_key_dt)[-need_days:]
            for d in use_days:
                date = d.get("date") or {}
                labels.append(f"{int(date.get('day', 0)):02d}.{int(date.get('month', 0)):02d}")
                timestamps.append(bandwidth_point_timestamp(date, {"hour": 0, "minute": 0}))
                rx_mbps.append(to_mbps_avg_per_day(d.get("rx", 0)))
                tx_mbps.append(to_mbps_avg_per_day(d.get("tx", 0)))
            if len(labels) < need_days:
                pad = need_days - len(labels)
                labels = [""] * pad + labels
                timestamps = [""] * pad + timestamps
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
            "timestamps": timestamps,
            "rx_mbps": rx_mbps,
            "tx_mbps": tx_mbps,
            "time_base": "node_local",
            "node_timezone": _node_timezone_name(),
            "totals": {"1d": sum_days(1), "7d": sum_days(7), "30d": sum_days(30)},
        }

    def list_interfaces(self, *, force: bool = False) -> dict:
        global _iface_list_cache
        now = time.monotonic()
        if not force and _iface_list_cache is not None:
            cached_at, cached = _iface_list_cache
            if now - cached_at < _IFACE_LIST_TTL_S:
                return cached

        groups = collect_interface_groups()
        primary = detect_primary_interface()
        all_ifaces: list[str] = []
        if primary and interface_exists(primary):
            all_ifaces.append(primary)
        for group in groups.values():
            for iface in group:
                if iface not in all_ifaces and interface_exists(iface):
                    all_ifaces.append(iface)
        if not all_ifaces:
            stats = _net_if_stats()
            all_ifaces = [name for name in list(stats.keys())[:5] if name != "lo"] or ["eth0"]
        result = {
            "interfaces": all_ifaces,
            "groups": groups,
            "primary_interface": primary,
            "vnstat_available": is_vnstat_available(),
        }
        _iface_list_cache = (now, result)
        return result

    def sample_interface_throughput(
        self,
        interface_names: list[str] | None = None,
        *,
        interval: float = 0.8,
        max_interfaces: int = 6,
    ) -> list[dict]:
        """Instant RX/TX Mbps per interface (short psutil sample)."""
        interval = max(0.3, min(float(interval), 2.0))
        names = [str(name).strip() for name in (interface_names or []) if str(name).strip()]
        if not names:
            listed = self.list_interfaces()
            names = list(listed.get("interfaces") or [])
        if not names:
            primary = detect_primary_interface()
            if primary:
                names = [primary]

        pernic = psutil.net_io_counters(pernic=True)
        stats = _net_if_stats()
        valid = [name for name in names if name in pernic][:max_interfaces]
        if not valid:
            return []

        snap1 = {name: pernic[name] for name in valid}
        time.sleep(interval)
        pernic2 = psutil.net_io_counters(pernic=True)

        rows: list[dict] = []
        for name in valid:
            current = pernic2.get(name)
            previous = snap1.get(name)
            if current is None or previous is None:
                continue
            delta_rx = max(int(current.bytes_recv) - int(previous.bytes_recv), 0)
            delta_tx = max(int(current.bytes_sent) - int(previous.bytes_sent), 0)
            rx_mbps = round((delta_rx * 8) / (interval * 1_000_000), 2)
            tx_mbps = round((delta_tx * 8) / (interval * 1_000_000), 2)
            iface_stats = stats.get(name)
            rows.append(
                {
                    "name": name,
                    "rx_mbps": rx_mbps,
                    "tx_mbps": tx_mbps,
                    "is_up": bool(iface_stats.isup) if iface_stats is not None else True,
                }
            )
        return rows

    def get_live_throughput(
        self,
        *,
        interval: float = 0.8,
        max_interfaces: int = 6,
        interface_names: list[str] | None = None,
    ) -> dict:
        names = [str(n).strip() for n in (interface_names or []) if str(n).strip()]
        if names:
            primary = names[0]
        else:
            listed = self.list_interfaces()
            names = list(listed.get("interfaces") or [])
            primary = listed.get("primary_interface")
        return {
            "primary_interface": primary,
            "interfaces": self.sample_interface_throughput(
                names,
                interval=interval,
                max_interfaces=max_interfaces,
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


_server_monitor: ServerMonitorService | None = None


def get_server_monitor() -> ServerMonitorService:
    """Return a process-wide monitor so psutil CPU deltas persist between polls."""
    global _server_monitor
    if _server_monitor is None:
        _server_monitor = ServerMonitorService()
        _server_monitor._ensure_cpu()
    return _server_monitor
