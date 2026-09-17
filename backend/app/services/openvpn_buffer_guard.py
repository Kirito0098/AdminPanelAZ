from __future__ import annotations

import subprocess

ALLOWED_UNITS = frozenset({"antizapret-udp", "antizapret-tcp", "vpn-udp", "vpn-tcp"})


def normalize_watch_unit(unit: str) -> str | None:
    """Normalize a requested OpenVPN server unit name to a short watch key.

    Accepts raw variants like:
    - "antizapret-udp"
    - "openvpn-server@vpn-udp"
    - "openvpn-server@vpn-udp.service"
    - "vpn-tcp.service"
    Returns the short name ("antizapret-udp", "vpn-udp", "vpn-tcp") if it is in
    the allowlist, otherwise ``None``.
    """
    u = (unit or "").strip()
    if not u:
        return None
    if u.startswith("openvpn-server@"):
        u = u.split("@", 1)[1]
    if u.endswith(".service"):
        u = u[: -len(".service")]
    return u if u in ALLOWED_UNITS else None


def journal_unit_name(unit: str) -> str | None:
    """Return full systemd unit name for an allowed watch unit."""
    name = normalize_watch_unit(unit)
    if not name:
        return None
    return f"openvpn-server@{name}.service"


def fetch_unit_journal(unit: str, window_seconds: int) -> dict:
    """Fetch recent journal entries for an OpenVPN server unit.

    Returns a dict:
    { "ok": bool, "unit": str, "text": str, "error": str | None }
    """
    name = normalize_watch_unit(unit)
    if not name:
        return {"ok": False, "unit": unit, "text": "", "error": "Недопустимый unit"}

    svc = journal_unit_name(name)
    if svc is None:
        return {"ok": False, "unit": unit, "text": "", "error": "Недопустимый unit"}

    window_seconds = max(5, min(int(window_seconds), 600))
    try:
        result = subprocess.run(
            ["journalctl", "-u", svc, f"--since=-{window_seconds} seconds", "--no-pager", "-o", "cat"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "unit": name, "text": "", "error": str(exc)}

    # 1 is "no entries"; treat as success with empty text.
    if result.returncode not in (0, 1):
        err = (result.stderr or result.stdout or "journalctl failed").strip()
        return {"ok": False, "unit": name, "text": "", "error": err}

    return {"ok": True, "unit": name, "text": result.stdout or "", "error": None}

