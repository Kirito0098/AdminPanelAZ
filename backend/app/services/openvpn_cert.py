"""OpenVPN client certificate expiry helpers."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone

_CERT_BLOCK_RE = re.compile(
    r"<cert>\s*(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)\s*</cert>",
    re.DOTALL,
)

_ENDDATE_RE = re.compile(
    r"notAfter\s*=\s*"
    r"(?P<mon>[A-Za-z]{3})\s+(?P<day>\d{1,2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+(?P<year>\d{4})\s+GMT"
)

_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def extract_pem_from_ovpn(content: str) -> str | None:
    match = _CERT_BLOCK_RE.search(content or "")
    return match.group(1).strip() if match else None


def cert_not_after_utc(pem: str) -> datetime | None:
    if not pem:
        return None
    try:
        result = subprocess.run(
            ["openssl", "x509", "-noout", "-enddate"],
            input=pem,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    match = _ENDDATE_RE.search(result.stdout or "")
    if not match:
        return None
    month = _MONTHS.get(match.group("mon"))
    if not month:
        return None
    try:
        return datetime(
            int(match.group("year")),
            month,
            int(match.group("day")),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def cert_days_remaining_from_pem(pem: str, *, now: datetime | None = None) -> int | None:
    not_after = cert_not_after_utc(pem)
    if not_after is None:
        return None
    current = now or datetime.now(timezone.utc)
    if not_after <= current:
        return 0
    return (not_after - current).days


def cert_days_remaining_from_ovpn_content(content: str, *, now: datetime | None = None) -> int | None:
    pem = extract_pem_from_ovpn(content)
    if not pem:
        return None
    return cert_days_remaining_from_pem(pem, now=now)


def resolve_openvpn_cert_days_remaining(adapter, client_name: str) -> int | None:
    """Read remaining certificate days from the first OpenVPN profile on the active node."""
    from app.models import VpnType

    files = adapter.get_profile_files(client_name, VpnType.openvpn)
    if not files:
        return None
    try:
        content = adapter.read_profile_file(files[0]["path"])
    except Exception:
        return None
    return cert_days_remaining_from_ovpn_content(content)
