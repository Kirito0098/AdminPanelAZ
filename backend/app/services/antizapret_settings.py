"""Read/write AntiZapret setup file ({antizapret_path}/setup)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.antizapret_params import ANTIZAPRET_PARAMS, KNOWN_SETTING_KEYS


def normalize_flag(v: Any) -> str:
    if isinstance(v, (bool, int)):
        return "y" if v else "n"
    s = str(v).lower().strip()
    return "y" if s in ("y", "yes", "true", "1", "on") else "n"


def build_schema() -> list[dict[str, str]]:
    return [
        {
            "key": p["key"],
            "html_id": p["html_id"],
            "type": p["type"],
            "env": p.get("env", ""),
            "param_label": p.get("param_label", p.get("env", "")),
            "title": p.get("title", ""),
            "description": p.get("description", ""),
        }
        for p in ANTIZAPRET_PARAMS
    ]


def read_setup_env_value(setup_path: Path, env_name: str, default: str = "") -> str:
    try:
        content = setup_path.read_text(encoding="utf-8")
    except OSError:
        return default
    match = re.search(rf"^{re.escape(env_name)}=(.+)$", content, re.M | re.I)
    return match.group(1).strip() if match else default


def is_openvpn_verbose_log_enabled(setup_path: Path) -> bool:
    return read_setup_env_value(setup_path, "OPENVPN_LOG", "n").lower() == "y"


def read_antizapret_settings(setup_path: Path) -> dict[str, str]:
    """Read setup file and return {key: value} for all ANTIZAPRET_PARAMS."""
    try:
        content = setup_path.read_text(encoding="utf-8")
    except OSError:
        content = ""

    settings: dict[str, str] = {}
    for p in ANTIZAPRET_PARAMS:
        key, env, typ, default = p["key"], p["env"], p["type"], p["default"]
        if typ == "string":
            m = re.search(rf"^{re.escape(env)}=(.+)$", content, re.M | re.I)
            settings[key] = m.group(1).strip() if m else default
        else:
            m = re.search(rf"^{re.escape(env)}=([yn])$", content, re.M | re.I)
            settings[key] = m.group(1).lower() if m else default
    return settings


def update_antizapret_settings(setup_path: Path, new_settings: dict[str, Any]) -> dict[str, Any]:
    """Apply partial updates to setup file. Unknown keys are ignored."""
    if not isinstance(new_settings, dict):
        raise ValueError("Ожидается JSON-объект")

    desired: dict[str, str] = {}
    for p in ANTIZAPRET_PARAMS:
        key = p["key"]
        if key not in new_settings:
            continue
        v = new_settings[key]
        env = p["env"]
        desired[env] = normalize_flag(v) if p["type"] == "flag" else str(v).strip()

    if not desired:
        return {
            "success": True,
            "message": "Нечего обновлять",
            "changes": 0,
            "needs_apply": False,
            "warnings": [],
        }

    try:
        lines = setup_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        lines = []

    new_lines: list[str] = []
    found: set[str] = set()
    changes = 0

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        key_part = stripped.split("=", 1)[0].strip()
        if key_part in desired:
            val = desired[key_part]
            comment = " " + stripped.split("#", 1)[1].strip() if "#" in stripped else ""
            new_lines.append(f"{key_part}={val}{comment}\n")
            found.add(key_part)
            changes += 1
        else:
            new_lines.append(line)

    for env, val in desired.items():
        if env not in found:
            new_lines.append(f"{env}={val}\n")
            changes += 1

    if changes > 0:
        setup_path.parent.mkdir(parents=True, exist_ok=True)
        setup_path.write_text("".join(new_lines), encoding="utf-8")

    return {
        "success": True,
        "message": "Настройки сохранены" if changes > 0 else "Нечего обновлять",
        "changes": changes,
        "needs_apply": changes > 0,
        "warnings": [],
    }


def filter_known_keys(updates: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in updates.items() if k in KNOWN_SETTING_KEYS}


OPENVPN_BACKUP_TCP_PORT443_WARNING = (
    "OPENVPN_BACKUP_TCP=y поднимает OpenVPN TCP на 80/443/504/508 и конфликтует с HTTPS панели на 443. "
    "Смените «Публичный порт HTTPS» в Настройки → Адрес сайта и HTTPS (HTTPS_PUBLIC_PORT), "
    "иначе после doall.sh панель может стать недоступна."
)


def panel_https_port_is_443(https_public_port: str | None) -> bool:
    port = (https_public_port or "").strip() or "443"
    return port == "443"


def openvpn_backup_tcp_conflict_warnings(
    new_settings: dict[str, Any],
    *,
    https_public_port: str | None,
) -> list[str]:
    """Soft warnings when enabling OPENVPN_BACKUP_TCP while panel HTTPS is on 443."""
    if "OPENVPN_BACKUP_TCP" not in new_settings:
        return []
    if normalize_flag(new_settings["OPENVPN_BACKUP_TCP"]) != "y":
        return []
    if not panel_https_port_is_443(https_public_port):
        return []
    return [OPENVPN_BACKUP_TCP_PORT443_WARNING]


AZ_PANEL_DOMAIN_CONFLICT_HINT = (
    "Через конфиг AntiZapret этот адрес уходит в туннель, и локальная панель "
    "становится недоступна. Задайте отдельный домен для панели "
    "(например panel.example.com), а для VPN оставьте свой (vpn.example.com)."
)

_AZ_VPN_HOST_SETTING_KEYS = ("openvpn_host", "wireguard_host")


def normalize_hostname(value: str | None) -> str:
    """Normalize a host/domain for equality checks (lowercase, no port/path/scheme)."""
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0]
    if raw.startswith("[") and "]" in raw:
        raw = raw[1 : raw.index("]")]
    else:
        raw = raw.split(":", 1)[0]
    return raw.rstrip(".")


def default_antizapret_setup_path() -> Path:
    from app.config import get_settings

    return get_settings().antizapret_path / "setup"


def read_az_vpn_hosts(setup_path: Path | None = None) -> set[str]:
    """Return non-empty OPENVPN_HOST / WIREGUARD_HOST from AntiZapret setup."""
    path = setup_path if setup_path is not None else default_antizapret_setup_path()
    hosts: set[str] = set()
    for env_name in ("OPENVPN_HOST", "WIREGUARD_HOST"):
        host = normalize_hostname(read_setup_env_value(path, env_name, ""))
        if host:
            hosts.add(host)
    return hosts


def az_hosts_matching_domain(domain: str | None, setup_path: Path | None = None) -> list[str]:
    """AZ VPN hosts that equal the given panel/shared domain (sorted)."""
    panel = normalize_hostname(domain)
    if not panel:
        return []
    return sorted(host for host in read_az_vpn_hosts(setup_path) if host == panel)


def format_az_panel_domain_conflict_message(
    domain: str | None,
    matching_hosts: list[str] | None = None,
    *,
    setup_path: Path | None = None,
) -> str | None:
    """Human-readable error when panel domain equals AZ VPN host(s)."""
    hosts = matching_hosts if matching_hosts is not None else az_hosts_matching_domain(domain, setup_path)
    if not hosts:
        return None
    host_list = ", ".join(hosts)
    panel = normalize_hostname(domain) or (domain or "").strip()
    return (
        f"Домен панели «{panel}» совпадает с OPENVPN_HOST / WIREGUARD_HOST AntiZapret ({host_list}). "
        f"{AZ_PANEL_DOMAIN_CONFLICT_HINT}"
    )


def az_host_updates_conflict_with_panel_domain(
    new_settings: dict[str, Any],
    panel_domain: str | None,
) -> str | None:
    """Error when saving openvpn_host/wireguard_host equal to panel DOMAIN."""
    panel = normalize_hostname(panel_domain)
    if not panel:
        return None
    colliding: list[str] = []
    for key in _AZ_VPN_HOST_SETTING_KEYS:
        if key not in new_settings:
            continue
        host = normalize_hostname(str(new_settings.get(key) or ""))
        if host and host == panel:
            colliding.append(host)
    if not colliding:
        return None
    unique = sorted(set(colliding))
    return (
        f"Нельзя задать OPENVPN_HOST / WIREGUARD_HOST равным домену панели «{panel}» "
        f"({', '.join(unique)}). {AZ_PANEL_DOMAIN_CONFLICT_HINT}"
    )


def shared_domain_conflicts_with_panel_domain(
    shared_domain: str | None,
    panel_domain: str | None,
) -> str | None:
    """Error when HA shared_domain equals panel DOMAIN (it becomes AZ VPN host)."""
    shared = normalize_hostname(shared_domain)
    panel = normalize_hostname(panel_domain)
    if not shared or not panel or shared != panel:
        return None
    return (
        f"Общий домен HA «{shared}» совпадает с доменом панели. "
        f"Он записывается в OPENVPN_HOST / WIREGUARD_HOST. {AZ_PANEL_DOMAIN_CONFLICT_HINT}"
    )
