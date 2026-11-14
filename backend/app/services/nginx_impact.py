"""What a full nginx update would change on this host, and what it could break.

``build_nginx_impact`` is a read-only preview for the server-config screen. It parses the vhosts that
nginx actually loads and answers three questions:

* which vhosts belong to the panel, the client portal, StatusOpenVPN or somebody else;
* whether the panel is a dedicated vhost or a snippet included into a foreign/StatusOpenVPN vhost
  (``integration_mode``);
* which panel-vhost locations and global snippets a re-render from the templates would drop.

The detector never writes anything and never calls ``nginx -t``/``systemctl``: it is safe to run from
the panel. Directory overrides (also used by ``scripts/nginx-common.sh``) make it testable:
``NGINX_SITES_ENABLED_DIR``, ``NGINX_SITES_AVAILABLE_DIR``, ``NGINX_CONF_D_DIR``. The StatusOpenVPN
installer path can be overridden with ``STATUS_OPENVPN_SETUP`` (default ``/root/web/setup``).

Contract::

    {
      "nginx_seen": bool,
      "panel_domain": str,
      "integration_mode": "dedicated_vhost" | "subpath_snippet" | "unknown",
      "panel_vhost": str | None,
      "panel_snippet_includes": [str],
      "vhosts": [
        {"host": str, "role": "panel" | "portal" | "other" | "statusopenvpn",
         "same_domain": bool, "will_change": bool, "note": str | None}
      ],
      "foreign_locations": [{"path": str, "project": str, "target": str | None}],
      "global_changes": [str],          # server_names_hash | privacy-log | default-deny
      "warnings": [str],
      "status_openvpn": {
        "detected": bool, "in_nginx": bool, "outside_nginx": bool,
        "domain": str | None, "path": str | None, "detail": str | None
      } | None,
    }

``same_domain`` means "this host is the panel host" (StatusOpenVPN sharing the panel domain is the
dangerous case). ``will_change`` is true only for panel/portal vhosts that an update re-renders; in
``subpath_snippet`` mode the shared vhost is foreign and stays untouched. ``panel_vhost`` is the
dedicated panel file, or the foreign/StatusOpenVPN file that includes the panel snippet.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

DEFAULT_SITES_ENABLED = Path("/etc/nginx/sites-enabled")
DEFAULT_SITES_AVAILABLE = Path("/etc/nginx/sites-available")
DEFAULT_CONF_D = Path("/etc/nginx/conf.d")
DEFAULT_STATUS_SETUP = Path("/root/web/setup")
PANEL_TEMPLATE = Path("deploy") / "nginx" / "adminpanelaz.conf.template"

# Locations the panel templates and their rendered root vhost own (prefixes are matched as prefixes).
PANEL_LOCATION_PREFIXES = ("/api/", "/assets/", "/.well-known/acme-challenge/")
PANEL_LOCATION_EXACT = frozenset({"/", "/api", "/assets", "/.well-known/acme-challenge"})
STATUS_PROXY_PORT = 1234

_SERVER_RE = re.compile(r"(?<![\w/])server\s*\{")
_SERVER_NAME_RE = re.compile(r"(?<![\w/])server_name\s+([^;]+);")
_LOCATION_RE = re.compile(r"(?<![\w/])location\s+(?:(?:=|~\*|~|\^~)\s*)?(/[^\s{;]*)\s*\{")
_PROXY_PASS_RE = re.compile(r"(?<![\w/])proxy_pass\s+([^;]+);")
_PANEL_SNIPPET_RE = re.compile(r"(?<![\w/])include\s+\S*/?(snippets/adminpanelaz-[^;\s]+)\s*;")
_STATUS_SCRIPT_RE = re.compile(r"(?<![\w/])proxy_set_header\s+X-Script-Name\s+/status(?:\s|;)")
_COMMENT_RE = re.compile(r"#[^\n]*")
_PORT_RE = re.compile(r":(\d+)(?:[/\s;]|$)")


def _env_dir(name: str, default: Path) -> Path:
    value = (os.environ.get(name) or "").strip()
    return Path(value) if value else default


def _normalize_domain(value: str) -> str:
    host = (value or "").strip().lower().rstrip(".")
    return host.split(":")[0] if host else ""


def _strip_comments(text: str) -> str:
    # Comments cannot open a server block or a location, and a commented-out include must not count.
    return _COMMENT_RE.sub("", text)


def _iter_server_blocks(text: str):
    """Yield the inner text of every ``server { ... }`` block (brace-counted, no regex nesting)."""
    for match in _SERVER_RE.finditer(text):
        depth = 1
        index = match.end()
        while index < len(text):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield text[match.end() : index]
                    break
            index += 1


def _block_body(text: str, brace_index: int) -> str:
    depth = 0
    for index in range(brace_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_index + 1 : index]
    return ""


def _parse_locations(block: str) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _LOCATION_RE.finditer(block):
        path = match.group(1)
        if path in seen:
            continue
        seen.add(path)
        body = _block_body(block, match.end() - 1)
        proxy = _PROXY_PASS_RE.search(body)
        locations.append(
            {
                "path": path,
                "body": body,
                "target": proxy.group(1).strip() if proxy else None,
                "status_header": bool(_STATUS_SCRIPT_RE.search(body)),
            }
        )
    return locations


def _parse_vhost(path: Path, raw: str) -> dict[str, Any]:
    cleaned = _strip_comments(raw)
    hosts: list[str] = []
    locations: list[dict[str, Any]] = []
    for block in _iter_server_blocks(cleaned):
        for match in _SERVER_NAME_RE.finditer(block):
            for token in match.group(1).split():
                host = _normalize_domain(token)
                if host and host != "_" and host not in hosts:
                    hosts.append(host)
        for location in _parse_locations(block):
            if location["path"] not in {item["path"] for item in locations}:
                locations.append(location)
    includes = [f"snippets/{name.rsplit('/', 1)[-1]}" for name in _PANEL_SNIPPET_RE.findall(cleaned)]
    is_status = "# Created by StatusOpenVPN" in raw or (
        any(item["path"].startswith("/status/") for item in locations) and bool(_STATUS_SCRIPT_RE.search(raw))
    )
    return {
        "path": path,
        "raw": raw,
        "locations": locations,
        "hosts": hosts,
        "panel_snippet_includes": includes,
        "is_status_openvpn": is_status,
        "panel_owned": "AdminPanelAZ —" in raw or "# AdminPanelAZ" in raw,
    }


def _read_vhosts(directories: list[Path]) -> list[dict[str, Any]]:
    vhosts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for directory in directories:
        if not directory.is_dir():
            continue
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_file() and not entry.is_symlink():
                    continue
                real = str(entry.resolve())
                if real in seen:
                    continue
                raw = entry.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            seen.add(real)
            vhosts.append(_parse_vhost(entry, raw))
    return vhosts


def _proxy_port(target: str | None) -> int | None:
    if not target:
        return None
    match = _PORT_RE.search(target)
    return int(match.group(1)) if match else None


def _template_locations(project_root: Path) -> set[str]:
    locations = set(PANEL_LOCATION_EXACT)
    template = project_root / PANEL_TEMPLATE
    if template.is_file():
        try:
            raw = template.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            raw = ""
        cleaned = _strip_comments(raw)
        for block in _iter_server_blocks(cleaned):
            locations.update(item["path"] for item in _parse_locations(block))
    return locations


def _is_panel_location(path: str, known: set[str], panel_port: int | None, body: str) -> bool:
    if path.startswith("/status/"):
        return False
    if path in known or path in PANEL_LOCATION_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in PANEL_LOCATION_PREFIXES):
        return True
    if "include snippets/adminpanelaz-" in body:
        return True
    proxy = _PROXY_PASS_RE.search(body)
    if panel_port is not None and proxy is not None and _proxy_port(proxy.group(1).strip()) == panel_port:
        return True
    # Subpath guard/redirect (location = /az-panel { return 301 /az-panel/; }) is ours, not foreign.
    return bool(re.search(r"(?<![\w/])return\s+30[12378](?:\s|;)", body))


def _location_project(path: str, target: str | None, body: str) -> str:
    if path.startswith("/status/") or _STATUS_SCRIPT_RE.search(body) or _proxy_port(target) == STATUS_PROXY_PORT:
        return "StatusOpenVPN"
    return "unknown"


def _sibling_suffix(panel_domain: str) -> str:
    labels = panel_domain.split(".") if panel_domain else []
    if len(labels) > 2:
        return "." + ".".join(labels[1:])
    return panel_domain


def _is_sibling(host: str, panel_domain: str) -> bool:
    suffix = _sibling_suffix(panel_domain)
    if not suffix or host == panel_domain:
        return False
    if suffix.startswith("."):
        return host.endswith(suffix)
    return host == suffix or host.endswith("." + suffix)


def _setup_values(path: Path) -> dict[str, str] | None:
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    values: dict[str, str] = {}
    for key in ("DOMAIN", "HTTPS_ENABLED"):
        match = re.search(rf"(?m)^\s*(?:export\s+)?{key}\s*=\s*(.+?)\s*$", text)
        if match:
            values[key] = match.group(1).strip().strip("'\"")
    return values


def _global_changes(conf_d: Path, vhosts: list[dict[str, Any]]) -> list[str]:
    changes: list[str] = []
    texts: list[str] = []
    names: list[str] = []
    if conf_d.is_dir():
        try:
            entries = sorted(conf_d.glob("*.conf"), key=lambda item: item.name)
        except OSError:
            entries = []
        for entry in entries:
            try:
                texts.append(entry.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            names.append(entry.name)
    names.extend(item["path"].name for item in vhosts)
    content = "\n".join(texts) + "\n" + "\n".join(item["raw"] for item in vhosts)
    if "server_names_hash" in content:
        changes.append("server_names_hash")
    if "adminpanelaz_privacy" in content or any("adminpanelaz-privacy-log" in name for name in names):
        changes.append("privacy-log")
    if any("adminpanelaz-default-deny" in name for name in names):
        changes.append("default-deny")
    return changes


def _empty_impact(panel_domain: str) -> dict[str, Any]:
    return {
        "nginx_seen": False,
        "panel_domain": panel_domain,
        "integration_mode": "unknown",
        "panel_vhost": None,
        "panel_snippet_includes": [],
        "vhosts": [],
        "foreign_locations": [],
        "global_changes": [],
        "warnings": [],
        "status_openvpn": None,
    }


def build_nginx_impact(*, project_root: Path, panel_domain: str, portal_domain: str = "") -> dict[str, Any]:
    panel = _normalize_domain(panel_domain)
    portal = _normalize_domain(portal_domain)
    enabled = _env_dir("NGINX_SITES_ENABLED_DIR", DEFAULT_SITES_ENABLED)
    available = _env_dir("NGINX_SITES_AVAILABLE_DIR", DEFAULT_SITES_AVAILABLE)
    conf_d = _env_dir("NGINX_CONF_D_DIR", DEFAULT_CONF_D)
    if not enabled.is_dir() and not available.is_dir():
        return _empty_impact(panel)

    vhosts = _read_vhosts([enabled, available])
    rows: list[dict[str, Any]] = []
    panel_vhosts: list[dict[str, Any]] = []
    snippet_hosts: list[tuple[str, dict[str, Any]]] = []
    panel_domain_foreign: list[dict[str, Any]] = []
    snip_includes: list[str] = []
    for vhost in vhosts:
        if vhost["panel_snippet_includes"] and not vhost["panel_owned"]:
            for include in vhost["panel_snippet_includes"]:
                snippet_hosts.append((include, vhost))
                if include not in snip_includes:
                    snip_includes.append(include)
        for host in vhost["hosts"]:
            if vhost["is_status_openvpn"] and not vhost["panel_owned"]:
                role = "statusopenvpn"
            elif host == portal:
                role = "portal"
            elif host == panel and vhost["panel_snippet_includes"] and not vhost["panel_owned"]:
                role = "other"
            elif host == panel:
                role = "panel"
            else:
                role = "other"
            note = None
            if role == "other" and host == panel:
                note = "домен панели занят чужим vhost"
                if vhost not in panel_domain_foreign:
                    panel_domain_foreign.append(vhost)
            elif role == "other" and _is_sibling(host, panel):
                note = "соседний поддомен"
            rows.append(
                {
                    "host": host,
                    "role": role,
                    "same_domain": host == panel,
                    "will_change": False,
                    "note": note,
                }
            )
            if role == "panel" and vhost not in panel_vhosts:
                panel_vhosts.append(vhost)

    dedicated = panel_vhosts[0] if panel_vhosts else None
    if snippet_hosts:
        integration_mode = "subpath_snippet"
        panel_vhost = str(snippet_hosts[0][1]["path"])
    elif dedicated is not None:
        integration_mode = "dedicated_vhost"
        panel_vhost = str(dedicated["path"])
    else:
        integration_mode = "unknown"
        panel_vhost = None

    for row in rows:
        row["will_change"] = row["role"] in {"panel", "portal"} and integration_mode != "subpath_snippet"

    foreign_locations: list[dict[str, str | None]] = []
    warnings: list[str] = []
    if dedicated is not None:
        known = _template_locations(Path(project_root))
        panel_port = next(
            (_proxy_port(item["target"]) for item in dedicated["locations"] if item["path"] == "/"),
            None,
        )
        for location in dedicated["locations"]:
            if _is_panel_location(location["path"], known, panel_port, location["body"]):
                continue
            foreign_locations.append(
                {
                    "path": location["path"],
                    "project": _location_project(location["path"], location["target"], location["body"]),
                    "target": location["target"],
                }
            )

    for include, vhost in snippet_hosts:
        host = vhost["hosts"][0] if vhost["hosts"] else vhost["path"].name
        warnings.append(
            f"Панель обслуживается через {include} в vhost {host} ({vhost['path']}) — "
            "шаг nginx не должен переписывать этот vhost; nginx по умолчанию выключен, snippet обновляйте вручную."
        )
        if vhost["is_status_openvpn"]:
            warnings.append(
                "Vhost общий со StatusOpenVPN: обновление должно сохранить location /status/ и X-Script-Name /status."
            )

    if foreign_locations:
        paths = ", ".join(str(item["path"]) for item in foreign_locations)
        warnings.append(
            f"В vhost панели ({panel_vhost}) есть чужие location: {paths} — "
            "шаг nginx пересобирает vhost из шаблона и может их удалить."
        )
        if any(item["project"] == "StatusOpenVPN" for item in foreign_locations):
            warnings.append(
                "Обновление nginx может удалить /status/ и сломать StatusOpenVPN — "
                "сначала проверьте vhost и сохраните блок /status/."
            )

    if panel_domain_foreign and integration_mode != "subpath_snippet":
        warnings.append(
            f"На домене панели {panel} есть чужой vhost ({panel_domain_foreign[0]['path']}) — "
            "если панель работает в подпути, шаг nginx не должен его менять."
        )

    status_vhosts = [vhost for vhost in vhosts if vhost["is_status_openvpn"] and not vhost["panel_owned"]]
    foreign_status = any(item["project"] == "StatusOpenVPN" for item in foreign_locations)
    any_status_location = any(
        location["path"].startswith("/status/") for vhost in vhosts for location in vhost["locations"]
    )
    in_nginx = bool(status_vhosts) or foreign_status or any_status_location
    setup_path = Path((os.environ.get("STATUS_OPENVPN_SETUP") or "").strip() or DEFAULT_STATUS_SETUP)
    setup = _setup_values(setup_path)
    status_openvpn: dict[str, Any] | None = None
    if in_nginx or setup is not None:
        status_domain = None
        for vhost in status_vhosts:
            if vhost["hosts"]:
                status_domain = vhost["hosts"][0]
                break
        if status_domain is None and setup is not None:
            status_domain = _normalize_domain(setup.get("DOMAIN", "")) or None
        status_path = None
        for vhost in vhosts:
            for location in vhost["locations"]:
                if location["path"].startswith("/status/"):
                    status_path = location["path"]
                    break
            if status_path:
                break
        outside = setup is not None and not in_nginx
        if outside:
            detail = (
                f"StatusOpenVPN установлен ({setup_path}), но в nginx нет /status/ — "
                "панель не видит и не может изменить эту установку."
            )
        elif foreign_status and not status_vhosts:
            detail = "StatusOpenVPN подключён внутри vhost панели (location /status/)."
        elif status_vhosts:
            domains = ", ".join(host for vhost in status_vhosts for host in vhost["hosts"]) or "без server_name"
            detail = f"StatusOpenVPN найден в nginx: {domains}."
        elif any_status_location:
            detail = "В nginx есть location /status/, но vhost не опознан как StatusOpenVPN — проверьте вручную."
        else:
            detail = "StatusOpenVPN найден в nginx."
        status_openvpn = {
            "detected": True,
            "in_nginx": in_nginx,
            "outside_nginx": outside,
            "domain": status_domain or None,
            "path": status_path,
            "detail": detail,
        }

    return {
        "nginx_seen": True,
        "panel_domain": panel,
        "integration_mode": integration_mode,
        "panel_vhost": panel_vhost,
        "panel_snippet_includes": snip_includes,
        "vhosts": rows,
        "foreign_locations": foreign_locations,
        "global_changes": _global_changes(conf_d, vhosts),
        "warnings": warnings,
        "status_openvpn": status_openvpn,
    }
