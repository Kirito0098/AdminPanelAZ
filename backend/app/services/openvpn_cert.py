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
    hour, minute, second = (int(part) for part in match.group("time").split(":"))
    try:
        return datetime(
            int(match.group("year")),
            month,
            int(match.group("day")),
            hour,
            minute,
            second,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def parse_easyrsa_expiry(value: str) -> datetime | None:
    """Parse the ASN.1 UTCTime/GeneralizedTime expiry column of EasyRSA index.txt."""
    raw = (value or "").strip().upper()
    if not raw.endswith("Z"):
        return None
    digits = raw[:-1]
    if len(digits) == 12:
        fmt = "%y%m%d%H%M%S"
    elif len(digits) == 14:
        fmt = "%Y%m%d%H%M%S"
    else:
        return None
    try:
        return datetime.strptime(digits, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def days_remaining_until(not_after: datetime | None, *, now: datetime | None = None) -> int | None:
    """Whole days left until `not_after`; 0 once expired. Naive values are read as UTC."""
    if not_after is None:
        return None
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if not_after <= current:
        return 0
    return (not_after - current).days


def to_naive_utc(value: datetime | None) -> datetime | None:
    """Normalize to naive UTC for storage, matching the rest of the DB schema."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def parse_iso_expiry(value: str) -> datetime | None:
    """Parse ISO-8601 / EasyRSA-friendly expiry strings into aware UTC."""
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z") and "T" not in raw and len(raw) in (13, 15):
        return parse_easyrsa_expiry(raw)
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw.replace(" ", "T"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def expiry_map_from_iso_dict(raw: dict[str, str] | None) -> dict[str, datetime]:
    result: dict[str, datetime] = {}
    for cn, value in (raw or {}).items():
        not_after = parse_iso_expiry(str(value))
        if not_after is None:
            continue
        name = str(cn).strip()
        if name:
            result[name] = not_after
    return result


def cert_days_remaining_from_pem(pem: str, *, now: datetime | None = None) -> int | None:
    return days_remaining_until(cert_not_after_utc(pem), now=now)


def cert_days_remaining_from_ovpn_content(content: str, *, now: datetime | None = None) -> int | None:
    pem = extract_pem_from_ovpn(content)
    if not pem:
        return None
    return cert_days_remaining_from_pem(pem, now=now)


def resolve_openvpn_cert_not_after(adapter, client_name: str) -> datetime | None:
    """Read the certificate expiry date from the first OpenVPN profile on the active node."""
    from app.models import VpnType

    try:
        files = adapter.get_profile_files(client_name, VpnType.openvpn)
    except Exception:
        return None
    if not files:
        return None
    try:
        content = adapter.read_profile_file(files[0]["path"])
    except Exception:
        return None
    pem = extract_pem_from_ovpn(content)
    if not pem:
        return None
    return cert_not_after_utc(pem)


def resolve_openvpn_cert_days_remaining(adapter, client_name: str) -> int | None:
    """Read remaining certificate days from the first OpenVPN profile on the active node."""
    return days_remaining_until(resolve_openvpn_cert_not_after(adapter, client_name))


def refresh_config_cert_expiry(config, adapter) -> None:
    """Store the node's real certificate notAfter on an OpenVPN config row."""
    from app.models import VpnType

    if config.vpn_type != VpnType.openvpn:
        return
    not_after = resolve_openvpn_cert_not_after(adapter, config.client_name)
    if not_after is not None:
        config.cert_expires_at = to_naive_utc(not_after)
