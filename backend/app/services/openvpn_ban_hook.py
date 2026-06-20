"""Ensure OpenVPN client-connect.sh rejects clients listed in banned_clients.

AntiZapret runs the OpenVPN daemon as the unprivileged ``nobody`` user, so the
client-connect script cannot read files under ``/root`` (the default
``antizapret_path``). We therefore mirror the banned list into the OpenVPN
server directory (next to the connect script, world-readable) and point the
ban-check hook at that mirror instead of the root-owned source file.
"""

from __future__ import annotations

import re
from pathlib import Path

BAN_CHECK_START = "# BEGIN adminpanel ban check"
BAN_CHECK_END = "# END adminpanel ban check"

# OpenVPN invokes this script on every new connection. Modern AntiZapret keeps it
# under /etc/openvpn/server/scripts; older layouts placed it next to the install
# dir. We install the ban hook into every script that actually exists.
DEFAULT_CLIENT_CONNECT_PATHS = (
    Path("/etc/openvpn/server/scripts/client-connect.sh"),
)

MIRROR_FILENAME = "banned_clients"


def build_ban_check_block(banned_clients_path: Path) -> str:
    p = str(banned_clients_path)
    return (
        f"{BAN_CHECK_START}\n"
        f'if [ -f "{p}" ]; then\n'
        f'  if grep -qxF "$common_name" "{p}" 2>/dev/null; then\n'
        '    echo "Client $common_name is banned" >&2\n'
        "    exit 1\n"
        "  fi\n"
        "fi\n"
        f"{BAN_CHECK_END}"
    )


def _strip_existing_block(content: str) -> str:
    pattern = re.compile(
        re.escape(BAN_CHECK_START) + r".*?" + re.escape(BAN_CHECK_END) + r"\n?",
        re.DOTALL,
    )
    return pattern.sub("", content)


def _read_source_banned(antizapret_path: Path) -> str:
    source = antizapret_path / "config" / "banned_clients"
    try:
        return source.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _sync_readable_mirror(mirror_path: Path, content: str) -> None:
    """Write a copy of the banned list that the ``nobody`` user can read."""
    mirror_path.parent.mkdir(parents=True, exist_ok=True)
    mirror_path.write_text(content, encoding="utf-8")
    try:
        mirror_path.chmod(0o644)
    except OSError:
        pass


def _candidate_scripts(antizapret_path: Path) -> list[Path]:
    candidates: list[Path] = [antizapret_path / "client-connect.sh"]
    candidates.extend(DEFAULT_CLIENT_CONNECT_PATHS)
    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _install_into_script(script: Path, banned_content: str) -> dict:
    # Mirror lives in the OpenVPN server dir (script.parent.parent), e.g.
    # /etc/openvpn/server/banned_clients — readable by the nobody user.
    server_dir = script.parent.parent
    mirror_path = server_dir / MIRROR_FILENAME
    _sync_readable_mirror(mirror_path, banned_content)

    block = build_ban_check_block(mirror_path)
    content = script.read_text(encoding="utf-8", errors="replace")

    if block in content:
        return {
            "script": str(script),
            "mirror": str(mirror_path),
            "message": "hook_already_present",
            "changed": False,
        }

    cleaned = _strip_existing_block(content)
    if cleaned.startswith("#!"):
        idx = cleaned.find("\n")
        if idx == -1:
            new_content = cleaned + "\n\n" + block + "\n"
        else:
            new_content = cleaned[: idx + 1] + "\n" + block + "\n" + cleaned[idx + 1 :].lstrip("\n")
    else:
        new_content = block + "\n" + cleaned.lstrip("\n")

    script.write_text(new_content, encoding="utf-8")
    return {
        "script": str(script),
        "mirror": str(mirror_path),
        "message": "hook_installed",
        "changed": True,
    }


def ensure_openvpn_ban_check(
    antizapret_path: Path,
    *,
    client_connect_paths: tuple[Path, ...] | None = None,
) -> dict:
    antizapret_path = Path(antizapret_path)
    banned_content = _read_source_banned(antizapret_path)

    candidates = (
        list(client_connect_paths)
        if client_connect_paths is not None
        else _candidate_scripts(antizapret_path)
    )

    results: list[dict] = []
    for script in candidates:
        if script.is_file():
            results.append(_install_into_script(script, banned_content))

    if not results:
        return {
            "success": False,
            "message": "client-connect.sh не найден",
            "changed": False,
            "scripts": [str(path) for path in candidates],
        }

    changed = any(item["changed"] for item in results)
    return {
        "success": True,
        "message": "hook_installed" if changed else "hook_already_present",
        "changed": changed,
        "scripts": results,
    }
