"""OpenVPN client certificate expiry helpers."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from cryptography import x509

logger = logging.getLogger(__name__)

_CERT_BLOCK_RE = re.compile(
    r"<cert>\s*(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)\s*</cert>",
    re.DOTALL,
)



def extract_pem_from_ovpn(content: str) -> str | None:
    match = _CERT_BLOCK_RE.search(content or "")
    return match.group(1).strip() if match else None


def cert_not_after_utc(pem: str) -> datetime | None:
    if not pem:
        return None
    try:
        cert = x509.load_pem_x509_certificate(pem.encode())
        return cert.not_valid_after_utc
    except Exception as exc:
        logger.debug("cert notAfter parse failed: %s", exc)
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


def resolve_openvpn_cert_not_after(adapter, client_name: str) -> datetime | None:
    """Read the certificate expiry date from the first OpenVPN profile on the active node."""
    from app.models import VpnType

    try:
        files = adapter.get_profile_files(client_name, VpnType.openvpn)
    except Exception:
        logger.debug("cert expiry: profile list failed client=%s", client_name, exc_info=True)
        return None
    if not files:
        return None
    try:
        content = adapter.read_profile_file(files[0]["path"])
    except Exception:
        logger.debug("cert expiry: profile read failed client=%s", client_name, exc_info=True)
        return None
    pem = extract_pem_from_ovpn(content)
    if not pem:
        return None
    return cert_not_after_utc(pem)


def refresh_config_cert_expiry(config, adapter) -> None:
    """Store the node's real certificate notAfter on an OpenVPN config row."""
    from app.models import VpnType

    if config.vpn_type != VpnType.openvpn:
        return
    not_after = resolve_openvpn_cert_not_after(adapter, config.client_name)
    if not_after is not None:
        config.cert_expires_at = to_naive_utc(not_after)
