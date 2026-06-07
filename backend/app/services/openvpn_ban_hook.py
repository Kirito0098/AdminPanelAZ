"""Ensure OpenVPN client-connect.sh rejects clients listed in banned_clients."""

from __future__ import annotations

from pathlib import Path

BAN_CHECK_START = "# BEGIN adminpanel ban check"
BAN_CHECK_END = "# END adminpanel ban check"


def build_ban_check_block(antizapret_path: Path) -> str:
    az = str(antizapret_path)
    return (
        f"{BAN_CHECK_START}\n"
        f'if [ -f {az}/config/banned_clients ]; then\n'
        f'  if grep -qxF "$common_name" {az}/config/banned_clients 2>/dev/null; then\n'
        '    echo "Client $common_name is banned" >&2\n'
        "    exit 1\n"
        "  fi\n"
        "fi\n"
        f"{BAN_CHECK_END}"
    )


def ensure_openvpn_ban_check(antizapret_path: Path) -> dict:
    script = antizapret_path / "client-connect.sh"
    block = build_ban_check_block(antizapret_path)
    if not script.is_file():
        return {"success": False, "message": "client-connect.sh не найден", "changed": False}

    content = script.read_text(encoding="utf-8", errors="replace")
    if block in content:
        return {"success": True, "message": "hook_already_present", "changed": False}

    if content.startswith("#!"):
        idx = content.find("\n")
        if idx == -1:
            new_content = content + "\n\n" + block + "\n"
        else:
            new_content = content[: idx + 1] + "\n" + block + "\n" + content[idx + 1 :].lstrip("\n")
    else:
        new_content = block + "\n" + content.lstrip("\n")

    script.write_text(new_content, encoding="utf-8")
    return {"success": True, "message": "hook_installed", "changed": True}
