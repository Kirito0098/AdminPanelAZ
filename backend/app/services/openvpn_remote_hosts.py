from __future__ import annotations

import ipaddress
import json
import re

MAX_OPENVPN_REMOTE_HOSTS = 8

_REMOTE_RE = re.compile(
    r"^(?P<prefix>\s*)remote\s+(?P<host>\S+)\s+(?P<port>\d+)(?:\s+(?P<proto>\S+))?\s*$"
)
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


class RemoteHostsError(ValueError):
    """Validation error with a Russian message in args[0]."""


def validate_host(host: str) -> str:
    value = (host or "").strip()
    if not value:
        raise RemoteHostsError("Адрес не может быть пустым")
    if any(ch.isspace() for ch in value):
        raise RemoteHostsError("Адрес не должен содержать пробелы")
    if value.lower().startswith(("http://", "https://", "ftp://", "file://")):
        raise RemoteHostsError("Укажите IP или домен без схемы URL")
    if "/" in value or "\\" in value or "@" in value:
        raise RemoteHostsError("Недопустимые символы в адресе")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if not _HOSTNAME_RE.match(value):
        raise RemoteHostsError(f"Некорректный адрес: {value}")
    return value


def normalize_hosts(hosts: list[str] | None) -> list[str]:
    if not hosts:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in hosts:
        if raw is None or str(raw).strip() == "":
            continue
        h = validate_host(str(raw))
        key = h.lower()
        if key in seen:
            raise RemoteHostsError(f"Дубликат адреса: {h}")
        seen.add(key)
        out.append(h)
    if len(out) > MAX_OPENVPN_REMOTE_HOSTS:
        raise RemoteHostsError(f"Не больше {MAX_OPENVPN_REMOTE_HOSTS} адресов")
    return out


def parse_hosts_json(raw: str | None) -> list[str]:
    if raw is None or str(raw).strip() == "":
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    try:
        return normalize_hosts([str(x) for x in data])
    except RemoteHostsError:
        return []


def hosts_to_json(hosts: list[str]) -> str:
    return json.dumps(list(hosts), ensure_ascii=False)


def sync_openvpn_host_from_remotes(adapter, hosts: list[str]) -> list[str]:
    """Best-effort OPENVPN_HOST=hosts[0]. Empty list must not touch settings."""
    if not hosts:
        return []
    try:
        adapter.update_antizapret_settings({"openvpn_host": hosts[0]})
        return []
    except Exception as exc:  # noqa: BLE001 — best-effort; list already saved
        return [f"Не удалось обновить OPENVPN_HOST: {exc}"]


def apply_openvpn_remote_hosts(content: str, hosts: list[str]) -> str:
    if not hosts:
        return content
    lines = content.splitlines(keepends=True)
    pairs: list[tuple[str, str | None]] = []
    seen_pairs: set[tuple[str, str | None]] = set()
    remote_idxs: list[int] = []
    for i, line in enumerate(lines):
        bare = line[:-1] if line.endswith("\n") else line
        if bare.endswith("\r"):
            bare = bare[:-1]
        m = _REMOTE_RE.match(bare)
        if not m:
            continue
        remote_idxs.append(i)
        pair = (m.group("port"), m.group("proto"))
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            pairs.append(pair)
    if not remote_idxs or not pairs:
        return content
    new_remotes: list[str] = []
    for host in hosts:
        for port, proto in pairs:
            if proto:
                new_remotes.append(f"remote {host} {port} {proto}\n")
            else:
                new_remotes.append(f"remote {host} {port}\n")
    # Drop CRLF handling: emit \n; if original used \r\n, normalize block to \n (acceptable).
    first = remote_idxs[0]
    keep = [ln for i, ln in enumerate(lines) if i not in set(remote_idxs)]
    # Insert at original first remote position among remaining lines:
    # Rebuild: take lines before first remote, then new remotes, then lines after last remote
    # with all remotes removed.
    before = []
    after = []
    for i, ln in enumerate(lines):
        if i < first:
            before.append(ln)
        elif i in set(remote_idxs):
            continue
        else:
            after.append(ln)
    return "".join(before + new_remotes + after)
