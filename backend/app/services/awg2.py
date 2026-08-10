"""AZ-AWG2 (az-awg2 AmneziaWG 2.0 parallel layer) integration."""

from __future__ import annotations

import fcntl
import io
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import HTTPException, status

from app.services.ip_geo import is_local_geoip_loaded, parse_client_endpoint

AWG2_CLIENT_BIN = Path(os.environ.get("AWG2_CLIENT_BIN", "/usr/local/bin/awg-client"))
AWG2_OBFUSCATION_BIN = Path(os.environ.get("AWG2_OBFUSCATION_BIN", "/usr/local/bin/awg-obfuscation"))
AWG2_OVERLAY_DIR = Path(os.environ.get("AWG2_OVERLAY_DIR", "/opt/antizapret-awg"))
AWG2_AMNEZIA_DIR = Path(os.environ.get("AWG2_AMNEZIA_DIR", "/etc/amnezia/amneziawg"))
AWG2_CLIENT_DIR = AWG2_OVERLAY_DIR / "clients"
AWG2_SERVICES_ENV = AWG2_AMNEZIA_DIR / "services.env"
AWG2_CLIENT_LOCK = Path(os.environ.get("AWG2_CLIENT_LOCK", "/run/antizapret-awg-client.lock"))
AWG2_INSTALL_LOCK = Path(
    os.environ.get("AWG2_INSTALL_LOCK", "/run/antizapret-awg-install.lock")
)
AWG2_STATS_SCRIPT = Path(
    os.environ.get("AWG2_STATS_SCRIPT", str(AWG2_OVERLAY_DIR / "bin" / "awg_stats.py"))
)
AWG2_STATS_DB = Path(os.environ.get("AWG2_STATS_DB", str(AWG2_OVERLAY_DIR / "stats.db")))
AWG2_EXPIRY_TSV = Path(os.environ.get("AWG2_EXPIRY_TSV", str(AWG2_OVERLAY_DIR / "expiry.tsv")))
AWG2_ONLINE_WINDOW_S = 180
AWG2_TUNNELS = ("antizapret", "vpn")
AWG2_STATE_ARCHIVE_KIND = "az-awg2-state"
AWG2_NARROW_BACKUP_KIND = "az-awg2-narrow-backup"
AWG2_OBFUSCATION_PRESETS = frozenset({"router", "low", "medium", "high", "paranoid"})
AWG2_OBFUSCATION_TEMPLATES = frozenset({"quic", "tls", "web", "voip", "dns", "mixed"})
AWG2_OBFUSCATION_FPS = frozenset({"chrome", "firefox", "safari"})

AWG2_INSTALL_CMD = (
    "bash <(curl -fsSL https://raw.githubusercontent.com/blindtechnique/az-awg2/main/install.sh)"
)
AWG2_UPDATE_CMD = (
    "bash <(curl -fsSL https://raw.githubusercontent.com/blindtechnique/az-awg2/main/install.sh) --update"
)

_CLIENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
_TTL_RE = re.compile(r"^(?P<value>[1-9]\d*)\s*(?P<unit>[smhdSMHD])$")


def parse_ttl_to_seconds(ttl: str) -> int:
    raw = (ttl or "").strip()
    match = _TTL_RE.fullmatch(raw)
    if match is None:
        raise ValueError("Некорректный TTL. Используйте формат вроде 15m, 2h или 7d")
    value = int(match.group("value"))
    unit = match.group("unit").lower()
    factor = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
    }.get(unit)
    if factor is None:
        raise ValueError("Некорректный TTL")
    return value * factor


def compute_expires_at(ttl: str | None) -> datetime | None:
    if ttl is None or not ttl.strip():
        return None
    return datetime.utcnow() + timedelta(seconds=parse_ttl_to_seconds(ttl))


def read_expiry_map() -> dict[str, datetime]:
    """Parse `expiry.tsv` (`name<TAB>tunnel<TAB>unix_ts`) into `{name: expires_at}` (naive UTC).

    A client has one row per tunnel; the latest timestamp wins so the panel never expires a
    row earlier than the node itself would.
    """
    result: dict[str, datetime] = {}
    if not AWG2_EXPIRY_TSV.is_file():
        return result
    try:
        raw = AWG2_EXPIRY_TSV.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name = parts[0].strip()
        stamp = parts[2].strip()
        if not name or not stamp.isdigit():
            continue
        expires_at = datetime.utcfromtimestamp(int(stamp))
        current = result.get(name)
        if current is None or expires_at > current:
            result[name] = expires_at
    return result


class Awg2NotInstalledError(Exception):
    """az-awg2 layer is not installed on this node."""


class Awg2ReplicaNotInstalledError(Awg2NotInstalledError):
    """AZ-AWG2 replica is not installed enough for HA sync operations."""

    def __init__(self, message: str, *, install_command: str):
        super().__init__(message)
        self.install_command = install_command


class Awg2ClientNotFoundError(LookupError):
    """Requested AWG2 client was not found in stats or runtime dumps."""


def detect_awg2_installation() -> dict[str, Any]:
    bin_ok = AWG2_CLIENT_BIN.is_file() and os.access(AWG2_CLIENT_BIN, os.X_OK)
    overlay_ok = AWG2_OVERLAY_DIR.is_dir()
    amnezia_ok = AWG2_AMNEZIA_DIR.is_dir()
    missing: list[str] = []
    if not bin_ok:
        missing.append("awg_client")
    if not overlay_ok:
        missing.append("overlay_dir")
    if not amnezia_ok:
        missing.append("amnezia_dir")
    return {
        "installed": bin_ok and overlay_ok and amnezia_ok,
        "awg_client": bin_ok,
        "overlay_dir": overlay_ok,
        "amnezia_dir": amnezia_ok,
        "missing_components": missing,
    }


def is_awg2_installed() -> bool:
    return bool(detect_awg2_installation()["installed"])


def _ensure_installed() -> None:
    if not is_awg2_installed():
        raise Awg2NotInstalledError(
            "AZ-AWG2 не установлен на узле. Установите: " + AWG2_INSTALL_CMD
        )


def _resolve_awg2_profile_path(path: str) -> Path:
    file_path = Path(path).resolve()
    client_root = AWG2_CLIENT_DIR.resolve()
    if not file_path.is_relative_to(client_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ к файлу запрещён")
    return file_path


def is_awg2_profile_path(path: str) -> bool:
    try:
        _resolve_awg2_profile_path(path)
        return True
    except HTTPException:
        return False


def _flock_prefix() -> list[str]:
    if Path("/usr/bin/flock").is_file() or Path("/bin/flock").is_file():
        return ["flock", "-w", "30", str(AWG2_CLIENT_LOCK)]
    return []


def build_install_argv(
    mode: Literal["install", "update"],
    *,
    preset: str | None = None,
    template: str | None = None,
    mtu: int | None = None,
    fp: str = "chrome",
) -> list[str]:
    if mode not in {"install", "update"}:
        raise ValueError(f"unknown AWG2 install mode: {mode}")

    if mode == "update":
        return ["bash", "-lc", AWG2_UPDATE_CMD]

    args = [AWG2_INSTALL_CMD, "--no-bot"]
    preset_value = (preset or "").strip().lower()
    template_value = (template or "").strip().lower()
    fp_value = (fp or "chrome").strip().lower()

    if preset_value:
        if preset_value not in AWG2_OBFUSCATION_PRESETS:
            raise ValueError(f"Недопустимый preset: {preset}")
        if not template_value:
            raise ValueError("template is required when preset is set")
        if template_value not in AWG2_OBFUSCATION_TEMPLATES:
            raise ValueError(f"Недопустимый template: {template}")
        if fp_value not in AWG2_OBFUSCATION_FPS:
            raise ValueError(f"Недопустимый fp: {fp}")
        args.extend(
            [
                "--preset",
                shlex.quote(preset_value),
                "--template",
                shlex.quote(template_value),
                "--fp",
                shlex.quote(fp_value),
            ]
        )

    # Upstream install.sh has no --mtu CLI flag; surface mtu in the start event only.
    _ = mtu
    return ["bash", "-lc", " ".join(args)]


def base_installed() -> bool:
    base_root = Path("/root/antizapret")
    return any((base_root / name).is_file() for name in ("client.sh", "up.sh"))


def _acquire_install_lock():
    AWG2_INSTALL_LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = AWG2_INSTALL_LOCK.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def iter_install_stream_events(
    mode: Literal["install", "update"],
    *,
    preset: str | None = None,
    template: str | None = None,
    mtu: int | None = None,
    fp: str = "chrome",
) -> Iterator[dict[str, Any]]:
    lock_handle = None
    proc: subprocess.Popen[str] | None = None
    try:
        lock_handle = _acquire_install_lock()
        if lock_handle is None:
            yield {"event": "error", "detail": "Установка AZ-AWG2 уже выполняется: lock занят"}
            return

        if mode == "install" and not base_installed():
            yield {
                "event": "error",
                "detail": (
                    "Не найдена база AntiZapret на узле "
                    "(/root/antizapret/client.sh или /root/antizapret/up.sh). "
                    "Установите базу по SSH; панель не запускает install-base."
                ),
            }
            return

        argv = build_install_argv(
            mode,
            preset=preset,
            template=template,
            mtu=mtu,
            fp=fp,
        )
        yield {
            "event": "start",
            "mode": mode,
            "argv": argv,
            "mtu": mtu,
        }
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        stdout = proc.stdout
        if stdout is None:
            yield {"event": "error", "detail": "stdout установки недоступен"}
            return
        for line in iter(stdout.readline, ""):
            if line:
                yield {"event": "log", "line": line.rstrip("\n")}
        rc = proc.wait(timeout=600)
        yield {"event": "done", "return_code": rc, "success": rc == 0}
    except Exception as exc:
        yield {"event": "error", "detail": str(exc)}
    finally:
        if proc and proc.poll() is None:
            proc.kill()
        if lock_handle is not None:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            lock_handle.close()


def _read_kv_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _read_services_env() -> dict[str, str]:
    return _read_kv_file(AWG2_SERVICES_ENV)


def _ensure_replica_installed() -> None:
    missing: list[str] = []
    if not AWG2_CLIENT_BIN.is_file():
        missing.append("awg_client")
    if not AWG2_OVERLAY_DIR.is_dir():
        missing.append("overlay_dir")
    if not AWG2_AMNEZIA_DIR.is_dir():
        missing.append("amnezia_dir")
    if missing:
        raise Awg2ReplicaNotInstalledError(
            f"AZ-AWG2 replica is not installed: missing {', '.join(missing)}",
            install_command=AWG2_INSTALL_CMD,
        )


def _is_excluded_archive_path(path: Path) -> bool:
    if path.name == "stats.db" or path.suffix == ".pyc":
        return True
    return any(part in {"venv", "__pycache__"} for part in path.parts)


def _write_tree_to_archive(archive: tarfile.TarFile, root: Path, archive_prefix: str) -> None:
    if not root.is_dir():
        return
    for item in sorted(root.rglob("*")):
        if not item.is_file() or _is_excluded_archive_path(item.relative_to(root)):
            continue
        archive.add(item, arcname=f"{archive_prefix}/{item.relative_to(root).as_posix()}")


def _write_file_to_archive(archive: tarfile.TarFile, path: Path, arcname: str) -> None:
    if path.is_file():
        archive.add(path, arcname=arcname)


def _build_manifest(kind: str) -> bytes:
    return "\n".join(
        [
            f"kind={kind}",
            f"amnezia_dir={AWG2_AMNEZIA_DIR}",
            f"client_dir={AWG2_CLIENT_DIR}",
            f"expiry_tsv={AWG2_EXPIRY_TSV}",
        ]
    ).encode("utf-8")


def _write_manifest_to_archive(archive: tarfile.TarFile, kind: str) -> None:
    manifest = _build_manifest(kind)
    info = tarfile.TarInfo(name="MANIFEST")
    info.size = len(manifest)
    archive.addfile(info, io.BytesIO(manifest))


def _read_manifest_kind(path: Path) -> str | None:
    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "kind":
            return value.strip()
    return None


def _validate_narrow_backup_members(members: list[tarfile.TarInfo]) -> None:
    allowed_top_level = {"amneziawg", "clients", "awgstate", "MANIFEST"}
    forbidden_top_level = {"openvpn", "config", "knot", "client"}

    for member in members:
        name = member.name.rstrip("/")
        if not name:
            continue
        if name == "MANIFEST":
            continue

        parts = Path(name).parts
        if not parts:
            continue
        top_level = parts[0]
        if top_level in forbidden_top_level:
            raise ValueError(f"AWG2 narrow backup contains forbidden member: {name}")
        if top_level not in allowed_top_level:
            raise ValueError(f"AWG2 narrow backup contains unexpected member: {name}")
        if "stats.db" in parts:
            raise ValueError(f"AWG2 narrow backup contains forbidden member: {name}")
        if top_level == "awgstate" and name != "awgstate/expiry.tsv":
            raise ValueError(f"AWG2 narrow backup contains unexpected member: {name}")


def _replace_tree_from_snapshot(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        target.mkdir(parents=True, exist_ok=True)


def _tree_has_files(root: Path) -> bool:
    return root.is_dir() and any(item.is_file() for item in root.rglob("*"))


def _replace_awg2_snapshot(
    *,
    source_amnezia: Path,
    source_clients: Path,
    source_expiry: Path,
) -> None:
    if not _tree_has_files(source_amnezia) or not _tree_has_files(source_clients):
        raise ValueError(
            "AWG2 archive must contain both amneziawg/ and clients/ files before import"
        )

    _replace_tree_from_snapshot(source_amnezia, AWG2_AMNEZIA_DIR)
    _replace_tree_from_snapshot(source_clients, AWG2_CLIENT_DIR)
    if source_expiry.is_file():
        AWG2_EXPIRY_TSV.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_expiry, AWG2_EXPIRY_TSV)
    else:
        AWG2_EXPIRY_TSV.unlink(missing_ok=True)


def _stats_db_path() -> Path:
    if AWG2_STATS_DB.is_file():
        return AWG2_STATS_DB
    overlay_db = AWG2_OVERLAY_DIR / "stats.db"
    if overlay_db.is_file():
        return overlay_db
    return AWG2_STATS_DB


def _parse_overview_tsv(text: str) -> list[dict[str, Any]]:
    """Parse machine-readable overview: name iface online handshake_age rx tx."""
    clients: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        name, iface, online_raw, age_raw, rx_raw, tx_raw = parts[:6]
        if name.lower() == "name" and iface.lower() == "iface":
            continue
        try:
            online_flag = online_raw.strip().lower() in {"1", "true", "yes", "online"}
            age = int(float(age_raw))
            rx = int(float(rx_raw))
            tx = int(float(tx_raw))
        except ValueError:
            continue
        clients.append(
            {
                "name": name,
                "iface": iface,
                "online": online_flag,
                "handshake_age_s": age,
                "rx": rx,
                "tx": tx,
            }
        )
    return clients


def _clients_from_stats_db(db_path: Path) -> list[dict[str, Any]]:
    """Structured overview from stats.db (same ONLINE_WINDOW as awg_stats.py)."""
    now = int(time.time())
    clients: list[dict[str, Any]] = []
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT p.name, p.iface, t.rx_life, t.tx_life, t.last_handshake
                FROM peers p
                LEFT JOIN totals t ON p.pubkey = t.pubkey
                WHERE COALESCE(p.origin, 'awg2') = 'awg2'
                ORDER BY (COALESCE(t.rx_life, 0) + COALESCE(t.tx_life, 0)) DESC
                """
            ).fetchall()
    except sqlite3.Error:
        return []
    for name, iface, rx_life, tx_life, last_hs in rows:
        hs = int(last_hs or 0)
        age = (now - hs) if hs else None
        online = bool(hs and age is not None and age < AWG2_ONLINE_WINDOW_S)
        clients.append(
            {
                "name": str(name or ""),
                "iface": str(iface or ""),
                "online": online,
                "handshake_age_s": age,
                "rx": int(rx_life or 0),
                "tx": int(tx_life or 0),
            }
        )
    return clients


def _load_peer_names() -> dict[str, str]:
    """Map peer pubkey → client name from amneziawg server confs."""
    mapping: dict[str, str] = {}
    if not AWG2_AMNEZIA_DIR.is_dir():
        return mapping
    for conf in sorted(AWG2_AMNEZIA_DIR.glob("*.conf")):
        name: str | None = None
        try:
            lines = conf.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            s = line.strip()
            if s.startswith("#") and len(s) > 1:
                comment = s[1:].strip()
                low = comment.lower()
                if low.startswith("privatekey") or low.startswith("presharedkey"):
                    continue
                name = comment.split("=", 1)[1].strip() if low.startswith("client =") else comment
            elif s.lower().startswith("publickey"):
                pk = s.split("=", 1)[1].strip() if "=" in s else ""
                if pk:
                    mapping[pk] = name or pk[:8]
                name = None
    return mapping


def _parse_awg_dump(text: str, *, iface: str, names: dict[str, str], now: int) -> list[dict[str, Any]]:
    """Parse `awg show <iface> dump` peer rows (skip interface/header first line)."""
    clients: list[dict[str, Any]] = []
    for i, raw in enumerate(text.splitlines()):
        fields = raw.split("\t")
        if i == 0 or len(fields) < 8:
            continue
        try:
            handshake = int(fields[4] or 0)
            rx = int(fields[5] or 0)
            tx = int(fields[6] or 0)
        except ValueError:
            continue
        pubkey = fields[0]
        age = (now - handshake) if handshake else None
        online = bool(handshake and age is not None and age < AWG2_ONLINE_WINDOW_S)
        clients.append(
            {
                "name": names.get(pubkey, pubkey[:8] if pubkey else "unknown"),
                "iface": iface,
                "online": online,
                "handshake_age_s": age,
                "rx": rx,
                "tx": tx,
                "pubkey": pubkey,
            }
        )
    return clients


def _daily_rows_from_stats_db(db_path: Path, client_name: str) -> list[dict[str, Any]]:
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT d.day, SUM(COALESCE(d.rx, 0)), SUM(COALESCE(d.tx, 0))
                FROM daily d
                JOIN peers p ON p.pubkey = d.pubkey
                WHERE COALESCE(p.origin, 'awg2') = 'awg2' AND p.name = ?
                GROUP BY d.day
                ORDER BY d.day ASC
                """,
                (client_name,),
            ).fetchall()
    except sqlite3.Error:
        return []

    daily: list[dict[str, Any]] = []
    for day, rx, tx in rows:
        if day is None:
            continue
        day_value = str(day).strip()
        if day_value.isdigit() and len(day_value) >= 10:
            try:
                day_value = datetime.utcfromtimestamp(int(day_value)).strftime("%Y-%m-%d")
            except (OverflowError, OSError, ValueError):
                pass
        daily.append({"day": day_value, "rx": int(rx or 0), "tx": int(tx or 0)})
    return daily


def _client_stats_from_stats_db(db_path: Path, client_name: str, *, now: int) -> dict[str, Any] | None:
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT p.iface, t.rx_life, t.tx_life, t.last_handshake, t.endpoint
                FROM peers p
                LEFT JOIN totals t ON p.pubkey = t.pubkey
                WHERE COALESCE(p.origin, 'awg2') = 'awg2' AND p.name = ?
                ORDER BY COALESCE(t.last_handshake, 0) DESC, p.iface ASC
                """,
                (client_name,),
            ).fetchall()
    except sqlite3.Error:
        return None

    if not rows:
        return None

    rx_life = 0
    tx_life = 0
    online = False
    handshake_age_s: int | None = None
    endpoint: str | None = None
    best_handshake = -1

    for _iface, rx_value, tx_value, last_hs, endpoint_value in rows:
        rx_life += int(rx_value or 0)
        tx_life += int(tx_value or 0)
        hs = int(last_hs or 0)
        age = (now - hs) if hs else None
        if age is not None:
            if handshake_age_s is None or age < handshake_age_s:
                handshake_age_s = age
            if age < AWG2_ONLINE_WINDOW_S:
                online = True
        if endpoint_value and hs >= best_handshake:
            endpoint = str(endpoint_value)
            best_handshake = hs

    return {
        "name": client_name,
        "online": online,
        "endpoint": endpoint,
        "handshake_age_s": handshake_age_s,
        "rx_life": rx_life,
        "tx_life": tx_life,
        "daily": _daily_rows_from_stats_db(db_path, client_name),
    }


def _client_stats_from_dump(
    client_name: str,
    *,
    dump_by_iface: dict[str, str],
    now: int,
) -> dict[str, Any] | None:
    names = _load_peer_names()
    rx_life = 0
    tx_life = 0
    online = False
    handshake_age_s: int | None = None
    endpoint: str | None = None
    best_handshake = -1
    matched = False

    for _iface, dump_text in dump_by_iface.items():
        for i, raw in enumerate(dump_text.splitlines()):
            fields = raw.split("\t")
            if i == 0 or len(fields) < 8:
                continue
            pubkey = fields[0]
            resolved_name = names.get(pubkey, pubkey[:8] if pubkey else "unknown")
            if resolved_name != client_name:
                continue
            matched = True
            try:
                handshake = int(fields[4] or 0)
                rx = int(fields[5] or 0)
                tx = int(fields[6] or 0)
            except ValueError:
                continue
            rx_life += rx
            tx_life += tx
            age = (now - handshake) if handshake else None
            if age is not None:
                if handshake_age_s is None or age < handshake_age_s:
                    handshake_age_s = age
                if age < AWG2_ONLINE_WINDOW_S:
                    online = True
            endpoint_value = (fields[2] or "").strip() or None
            if endpoint_value and handshake >= best_handshake:
                endpoint = endpoint_value
                best_handshake = handshake

    if not matched:
        return None

    return {
        "name": client_name,
        "online": online,
        "endpoint": endpoint,
        "handshake_age_s": handshake_age_s,
        "rx_life": rx_life,
        "tx_life": tx_life,
        "daily": [],
    }


def _lookup_local_geo_for_endpoint(endpoint: str | None) -> dict[str, str | None] | None:
    parsed = parse_client_endpoint(endpoint)
    lookup_ip = parsed.get("lookup_ip")
    if not lookup_ip or not is_local_geoip_loaded():
        return None
    from app.services import geoip_local

    return geoip_local.lookup_geo_local(lookup_ip)


class Awg2Service:
    def ensure_installed(self) -> None:
        _ensure_installed()

    def validate_client_name(self, name: str) -> str:
        value = (name or "").strip()
        if not _CLIENT_NAME_RE.match(value):
            raise ValueError("Некорректное имя клиента")
        return value

    def _run_awg_client(self, *args: str, timeout: int = 120) -> str:
        _ensure_installed()
        cmd = [*_flock_prefix(), str(AWG2_CLIENT_BIN), *args]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "awg-client failed").strip()
            raise RuntimeError(err)
        return (completed.stdout or "").strip()

    def _run_obfuscation(self, *args: str, timeout: int = 180) -> str:
        _ensure_installed()
        if not AWG2_OBFUSCATION_BIN.is_file():
            raise RuntimeError(f"awg-obfuscation binary not found: {AWG2_OBFUSCATION_BIN}")
        cmd = [str(AWG2_OBFUSCATION_BIN), *args]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "awg-obfuscation failed").strip()
            raise RuntimeError(err)
        return (completed.stdout or "").strip()

    def _regen_all_clients(self) -> str:
        return self._run_awg_client("regen-all")

    def get_obfuscation(self) -> dict[str, Any]:
        _ensure_installed()
        meta = _read_kv_file(AWG2_AMNEZIA_DIR / "obfuscation.meta")
        env = _read_kv_file(AWG2_AMNEZIA_DIR / "obfuscation.env")
        params: dict[str, str] = {}
        for key, value in env.items():
            if key.startswith("AWG_"):
                params[key[4:]] = value
            else:
                params[key] = value
        mtu_raw = meta.get("META_MTU")
        mtu: Any = mtu_raw
        if mtu_raw is not None and str(mtu_raw).strip().isdigit():
            mtu = int(str(mtu_raw).strip())
        template = meta.get("META_TEMPLATE") or None
        host = meta.get("META_HOST") or None
        return {
            "preset": meta.get("META_PRESET"),
            "template": template,
            "fp": meta.get("META_FP"),
            "host": host,
            "mtu": mtu,
            "generated": meta.get("META_GENERATED"),
            "params": params,
        }

    def regenerate_obfuscation(self) -> dict[str, Any]:
        _ensure_installed()
        output = self._run_obfuscation("--regenerate")
        regen_out = self._regen_all_clients()
        profile = self.get_obfuscation()
        profile["output"] = output
        profile["regen_all"] = regen_out
        return profile

    def apply_obfuscation(
        self,
        preset: str,
        template: str,
        mtu: int | None = None,
        host: str | None = None,
        fp: str | None = None,
    ) -> dict[str, Any]:
        preset_value = (preset or "").strip().lower()
        template_value = (template or "").strip().lower()
        if preset_value not in AWG2_OBFUSCATION_PRESETS:
            raise ValueError(f"Недопустимый preset: {preset}")
        if template_value not in AWG2_OBFUSCATION_TEMPLATES:
            raise ValueError(f"Недопустимый template: {template}")

        fp_value: str | None = None
        if fp:
            fp_value = str(fp).strip().lower()
            if fp_value not in AWG2_OBFUSCATION_FPS:
                raise ValueError(f"Недопустимый fp: {fp}")

        _ensure_installed()

        args = ["--preset", preset_value, "--template", template_value, "--apply"]
        if mtu is not None:
            args.extend(["--mtu", str(int(mtu))])
        if host:
            args.extend(["--host", str(host).strip()])
        if fp_value:
            args.extend(["--fp", fp_value])

        output = self._run_obfuscation(*args)
        regen_out = self._regen_all_clients()
        profile = self.get_obfuscation()
        profile["output"] = output
        profile["regen_all"] = regen_out
        return profile

    def add_client(self, name: str, ttl: str | None = None) -> str:
        name = self.validate_client_name(name)
        ttl_value = ttl.strip() if ttl else None
        if ttl_value:
            parse_ttl_to_seconds(ttl_value)
        created: list[str] = []
        outputs: list[str] = []
        try:
            for tunnel in AWG2_TUNNELS:
                args = ["add", name, tunnel]
                if ttl_value:
                    args.extend(["--ttl", ttl_value])
                outputs.append(self._run_awg_client(*args))
                created.append(tunnel)
        except Exception:
            for tunnel in reversed(created):
                try:
                    self._run_awg_client("del", name, tunnel)
                except Exception:
                    pass
            raise
        return "\n".join(outputs)

    def delete_client(self, name: str) -> str:
        name = self.validate_client_name(name)
        outputs: list[str] = []
        for tunnel in AWG2_TUNNELS:
            conf = AWG2_CLIENT_DIR / tunnel / f"{tunnel}-{name}-am.conf"
            if not conf.is_file():
                continue
            try:
                outputs.append(self._run_awg_client("del", name, tunnel))
            except RuntimeError as exc:
                msg = str(exc).lower()
                if (
                    "не существует" in msg
                    or "not found" in msg
                    or "не найден" in msg
                ):
                    continue
                raise
        return "\n".join(outputs) or f"Клиент '{name}' удалён (файлов не было)"

    def expire_check(self) -> str:
        return self._run_awg_client("expire-check")

    def iter_install_stream_events(
        self,
        mode: Literal["install", "update"],
        *,
        preset: str | None = None,
        template: str | None = None,
        mtu: int | None = None,
        fp: str = "chrome",
    ) -> Iterator[dict[str, Any]]:
        return iter_install_stream_events(
            mode,
            preset=preset,
            template=template,
            mtu=mtu,
            fp=fp,
        )

    def read_expiry_map(self) -> dict[str, datetime]:
        """Parse the upstream `expiry.tsv` into `{client_name: expires_at}` (UTC, naive)."""
        return read_expiry_map()

    def get_profile_files(self, client_name: str) -> list[dict[str, str]]:
        name = self.validate_client_name(client_name)
        files: list[dict[str, str]] = []
        for tunnel in AWG2_TUNNELS:
            path = AWG2_CLIENT_DIR / tunnel / f"{tunnel}-{name}-am.conf"
            if path.is_file():
                files.append(
                    {
                        "protocol": "amneziawg2",
                        "variant": tunnel,
                        "path": str(path),
                        "filename": path.name,
                    }
                )
            for extra_suffix, kind in (
                (".vpn", "vpnuri"),
                ("-vpnuri.txt", "vpnuri"),
            ):
                extra = AWG2_CLIENT_DIR / tunnel / f"{tunnel}-{name}{extra_suffix}"
                if extra.is_file():
                    files.append(
                        {
                            "protocol": "amneziawg2",
                            "variant": tunnel,
                            "path": str(extra),
                            "filename": extra.name,
                            "kind": kind,
                        }
                    )
        return files

    def read_profile_file(self, path: str) -> str:
        file_path = _resolve_awg2_profile_path(path)
        if not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
        return file_path.read_text(encoding="utf-8", errors="replace")

    def write_profile_file(self, path: str, content: str) -> None:
        file_path = _resolve_awg2_profile_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content or "", encoding="utf-8")

    def get_health(self) -> dict[str, Any]:
        detected = detect_awg2_installation()
        return {
            **detected,
            "install_command": AWG2_INSTALL_CMD,
            "update_command": AWG2_UPDATE_CMD,
        }

    def get_status(self) -> dict[str, Any]:
        if not is_awg2_installed():
            raise Awg2NotInstalledError(
                "AZ-AWG2 не установлен на узле. Установите: " + AWG2_INSTALL_CMD
            )
        env = _read_services_env()
        return {
            "installed": True,
            "services_env": {
                "AZ_IFACE": env.get("AZ_IFACE"),
                "VPN_IFACE": env.get("VPN_IFACE"),
                "AZ_PORT": env.get("AZ_PORT"),
                "VPN_PORT": env.get("VPN_PORT"),
                "AZ_SUBNET": env.get("AZ_SUBNET"),
                "VPN_SUBNET": env.get("VPN_SUBNET"),
            },
            "client_counts": {
                "antizapret": len(self.list_clients("antizapret")),
                "vpn": len(self.list_clients("vpn")),
            },
        }

    def get_monitoring(self) -> dict[str, Any]:
        """Iface summary + clients overview (stats.db) or live dump fallback."""
        _ensure_installed()
        env = _read_services_env()
        iface_specs = [
            ("antizapret", env.get("AZ_IFACE"), env.get("AZ_PORT"), env.get("AZ_SUBNET")),
            ("vpn", env.get("VPN_IFACE"), env.get("VPN_PORT"), env.get("VPN_SUBNET")),
        ]
        dump_by_iface: dict[str, str] = {}
        ifaces: list[dict[str, Any]] = []
        for _tunnel, name, port, subnet in iface_specs:
            if not name:
                continue
            dump_text = self._awg_show_dump(name)
            dump_by_iface[name] = dump_text
            peer_count = 0
            for i, line in enumerate(dump_text.splitlines()):
                if i == 0:
                    continue
                if len(line.split("\t")) >= 8:
                    peer_count += 1
            ifaces.append(
                {
                    "name": name,
                    "port": port,
                    "subnet": subnet,
                    "peer_count": peer_count,
                }
            )

        stats_db = _stats_db_path()
        stats_file_present = stats_db.is_file()
        clients: list[dict[str, Any]] = []
        stats_available = False

        if stats_file_present:
            overview_text = self._run_stats_overview()
            clients = _parse_overview_tsv(overview_text)
            if not clients:
                clients = _clients_from_stats_db(stats_db)
            if clients:
                stats_available = True

        if not clients:
            names = _load_peer_names()
            now = int(time.time())
            for iface_name, dump_text in dump_by_iface.items():
                clients.extend(
                    _parse_awg_dump(dump_text, iface=iface_name, names=names, now=now)
                )
            stats_available = False

        return {
            "ifaces": ifaces,
            "clients": clients,
            "stats_available": stats_available,
        }

    def get_client_stats(self, name: str) -> dict[str, Any]:
        _ensure_installed()
        client_name = self.validate_client_name(name)
        now = int(time.time())
        payload: dict[str, Any] | None = None
        stats_db = _stats_db_path()
        if stats_db.is_file():
            payload = _client_stats_from_stats_db(stats_db, client_name, now=now)

        if payload is None:
            env = _read_services_env()
            dump_by_iface: dict[str, str] = {}
            for iface_name in (env.get("AZ_IFACE"), env.get("VPN_IFACE")):
                if not iface_name:
                    continue
                dump_by_iface[iface_name] = self._awg_show_dump(iface_name)
            payload = _client_stats_from_dump(client_name, dump_by_iface=dump_by_iface, now=now)

        if payload is None:
            raise Awg2ClientNotFoundError(f"AWG2 client not found: {client_name}")

        payload["geo"] = _lookup_local_geo_for_endpoint(payload.get("endpoint"))
        return payload

    def _run_stats_overview(self) -> str:
        script = AWG2_STATS_SCRIPT
        if not script.is_file():
            return ""
        try:
            completed = subprocess.run(
                [sys.executable, str(script), "overview"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env={
                    **os.environ,
                    "AWG_STATS_DB": str(_stats_db_path()),
                    "AWG_DIR": str(AWG2_AMNEZIA_DIR),
                },
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if completed.returncode != 0:
            return ""
        return completed.stdout or ""

    def _awg_show_dump(self, iface: str) -> str:
        awg_bin = shutil.which("awg") or "awg"
        try:
            completed = subprocess.run(
                [awg_bin, "show", iface, "dump"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if completed.returncode != 0:
            return ""
        return completed.stdout or ""

    def list_clients(self, tunnel: str = "antizapret") -> list[str]:
        if tunnel not in AWG2_TUNNELS:
            raise ValueError(f"unknown tunnel: {tunnel}")
        directory = AWG2_CLIENT_DIR / tunnel
        if not directory.is_dir():
            return []
        names: list[str] = []
        prefix = f"{tunnel}-"
        suffix = "-am.conf"
        for path in sorted(directory.glob(f"{prefix}*-am.conf")):
            stem = path.name
            if stem.startswith(prefix) and stem.endswith(suffix):
                names.append(stem[len(prefix) : -len(suffix)])
        return names

    def list_all_client_names(self) -> list[str]:
        names = set(self.list_clients("antizapret")) | set(self.list_clients("vpn"))
        return sorted(names)

    def export_state_archive(self) -> bytes:
        _ensure_replica_installed()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            _write_tree_to_archive(archive, AWG2_AMNEZIA_DIR, "amneziawg")
            _write_tree_to_archive(archive, AWG2_CLIENT_DIR, "clients")
            _write_file_to_archive(archive, AWG2_EXPIRY_TSV, "awgstate/expiry.tsv")
            _write_manifest_to_archive(archive, AWG2_STATE_ARCHIVE_KIND)
        return buffer.getvalue()

    def import_state_archive(self, data: bytes) -> None:
        if not data:
            raise ValueError("empty AWG2 archive")
        _ensure_replica_installed()

        with tempfile.TemporaryDirectory(prefix="awg2-import-") as temp_dir:
            temp_root = Path(temp_dir)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                archive.extractall(path=temp_root, filter="data")

            source_amnezia = temp_root / "amneziawg"
            source_clients = temp_root / "clients"
            source_expiry = temp_root / "awgstate" / "expiry.tsv"
            _replace_awg2_snapshot(
                source_amnezia=source_amnezia,
                source_clients=source_clients,
                source_expiry=source_expiry,
            )

    def export_narrow_backup(self) -> bytes:
        _ensure_replica_installed()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            _write_tree_to_archive(archive, AWG2_AMNEZIA_DIR, "amneziawg")
            _write_tree_to_archive(archive, AWG2_CLIENT_DIR, "clients")
            _write_file_to_archive(archive, AWG2_EXPIRY_TSV, "awgstate/expiry.tsv")
            _write_manifest_to_archive(archive, AWG2_NARROW_BACKUP_KIND)
        return buffer.getvalue()

    def import_narrow_backup(self, data: bytes) -> None:
        if not data:
            raise ValueError("empty AWG2 backup")
        _ensure_replica_installed()

        with tempfile.TemporaryDirectory(prefix="awg2-backup-restore-") as temp_dir:
            temp_root = Path(temp_dir)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                _validate_narrow_backup_members(archive.getmembers())
                archive.extractall(path=temp_root, filter="data")

            manifest_kind = _read_manifest_kind(temp_root / "MANIFEST")
            if manifest_kind != AWG2_NARROW_BACKUP_KIND:
                raise ValueError(
                    f"AWG2 backup MANIFEST kind must be {AWG2_NARROW_BACKUP_KIND}"
                )

            _replace_awg2_snapshot(
                source_amnezia=temp_root / "amneziawg",
                source_clients=temp_root / "clients",
                source_expiry=temp_root / "awgstate" / "expiry.tsv",
            )

    def apply_runtime(self) -> dict[str, Any]:
        _ensure_replica_installed()
        env = _read_services_env()
        interfaces = [
            iface.strip()
            for iface in (env.get("AZ_IFACE", ""), env.get("VPN_IFACE", ""))
            if iface and iface.strip()
        ]
        synced: list[str] = []
        restarted: list[str] = []
        errors: list[dict[str, str | None]] = []
        awg_bin = shutil.which("awg")

        if not interfaces:
            return {
                "success": False,
                "synced": synced,
                "restarted": restarted,
                "errors": [
                    {
                        "interface": None,
                        "stderr": "services.env does not define AZ_IFACE or VPN_IFACE",
                    }
                ],
            }

        for interface in interfaces:
            sync_error = "awg unavailable"
            if awg_bin:
                sync_error = self._sync_runtime_interface(interface)
                if sync_error is None:
                    synced.append(interface)
                    continue

            restart = subprocess.run(
                ["systemctl", "restart", f"awg-quick@{interface}"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if restart.returncode == 0:
                restarted.append(interface)
            else:
                errors.append(
                    {
                        "interface": interface,
                        "sync_error": sync_error,
                        "stderr": (restart.stderr or restart.stdout or "awg-quick restart failed").strip(),
                    }
                )

        return {
            "success": not errors,
            "synced": synced,
            "restarted": restarted,
            "errors": errors,
        }

    def _sync_runtime_interface(self, interface: str) -> str | None:
        strip_result = subprocess.run(
            ["awg-quick", "strip", interface],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if strip_result.returncode != 0:
            return (strip_result.stderr or strip_result.stdout or "awg-quick strip failed").strip()

        stripped_config = strip_result.stdout or ""
        if not stripped_config.strip():
            return "empty stripped config"

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
                temp_file.write(stripped_config)
                temp_path = temp_file.name
            sync_result = subprocess.run(
                ["awg", "syncconf", interface, temp_path],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if sync_result.returncode == 0:
                return None
            return (sync_result.stderr or sync_result.stdout or "awg syncconf failed").strip()
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
