"""EasyRSA PKI helpers: parse index.txt and validate OpenVPN profile certificates."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.models import VpnType
from app.services.openvpn_cert import cert_not_after_utc, extract_pem_from_ovpn

EASYRSA_INDEX_PATH = Path("/etc/openvpn/easyrsa3/pki/index.txt")

_CN_RE = re.compile(r"/CN=([^/\t]+)")
_SERIAL_OPENSSL_RE = re.compile(r"serial\s*=\s*([0-9A-Fa-f]+)", re.IGNORECASE)


@dataclass(frozen=True)
class EasyRsaIndexEntry:
    status: Literal["V", "R", "E"]
    expiry: str
    serial_hex: str
    common_name: str
    revocation_date: str | None = None


@dataclass(frozen=True)
class ProfileCertIssue:
    client_name: str
    path: str
    filename: str
    serial_hex: str | None
    status: str  # revoked | expired | unknown_serial | missing_cert | not_in_index


@dataclass(frozen=True)
class ProfileValidationResult:
    ready: bool
    issues: tuple[ProfileCertIssue, ...]


def _normalize_serial_hex(raw: str) -> str | None:
    value = (raw or "").strip().upper().replace("0X", "")
    if not value:
        return None
    try:
        if all(c in "0123456789ABCDEF" for c in value):
            if len(value) % 2 == 0 and len(value) <= 32:
                return value
        decimal = int(value, 10)
        hex_value = format(decimal, "X")
        if len(hex_value) % 2:
            hex_value = "0" + hex_value
        return hex_value.upper()
    except ValueError:
        return None


def parse_easyrsa_index(index_txt: str) -> list[EasyRsaIndexEntry]:
    entries: list[EasyRsaIndexEntry] = []
    for line in (index_txt or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        status = parts[0].strip().upper()
        if status not in {"V", "R", "E"}:
            continue
        cn_match = _CN_RE.search(parts[-1])
        if not cn_match:
            continue
        common_name = cn_match.group(1).strip()
        if status == "R":
            if len(parts) < 5:
                continue
            expiry = parts[1].strip()
            revocation_date = parts[2].strip() or None
            serial_hex = _normalize_serial_hex(parts[3])
        else:
            # EasyRSA keeps an empty revocation column for V/E:
            #   V\texpiry\t\tserial\tunknown\t/CN=...
            # Some fixtures omit that empty field:
            #   V\texpiry\tserial\tunknown\t/CN=...
            expiry = parts[1].strip()
            revocation_date = None
            if parts[2].strip() == "" and len(parts) >= 4:
                serial_hex = _normalize_serial_hex(parts[3])
            else:
                serial_hex = _normalize_serial_hex(parts[2])
        if not serial_hex:
            continue
        entries.append(
            EasyRsaIndexEntry(
                status=status,  # type: ignore[arg-type]
                expiry=expiry,
                serial_hex=serial_hex,
                common_name=common_name,
                revocation_date=revocation_date,
            )
        )
    return entries


def cert_serial_hex_from_pem(pem: str) -> str | None:
    if not pem:
        return None
    try:
        result = subprocess.run(
            ["openssl", "x509", "-noout", "-serial"],
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
    match = _SERIAL_OPENSSL_RE.search(result.stdout or "")
    if not match:
        return None
    return _normalize_serial_hex(match.group(1))


def serial_status(serial_hex: str, entries: list[EasyRsaIndexEntry]) -> str | None:
    normalized = _normalize_serial_hex(serial_hex)
    if not normalized:
        return None
    for entry in entries:
        if entry.serial_hex == normalized:
            return entry.status
    return None


def find_valid_serials(cn: str, entries: list[EasyRsaIndexEntry]) -> list[str]:
    name = (cn or "").strip()
    return [
        entry.serial_hex
        for entry in entries
        if entry.common_name == name and entry.status == "V"
    ]


def is_serial_revoked(serial_hex: str, entries: list[EasyRsaIndexEntry]) -> bool:
    return serial_status(serial_hex, entries) == "R"


def read_easyrsa_index_from_path(path: Path | None = None) -> str:
    file_path = path or EASYRSA_INDEX_PATH
    if not file_path.is_file():
        return ""
    return file_path.read_text(encoding="utf-8", errors="replace")


def load_easyrsa_index(adapter) -> list[EasyRsaIndexEntry]:
    if hasattr(adapter, "read_easyrsa_index"):
        index_txt = adapter.read_easyrsa_index()
    else:
        index_txt = read_easyrsa_index_from_path()
    return parse_easyrsa_index(index_txt)


def _issue_for_profile(
    *,
    client_name: str,
    path: str,
    filename: str,
    content: str,
    entries: list[EasyRsaIndexEntry],
    now: datetime,
) -> ProfileCertIssue | None:
    pem = extract_pem_from_ovpn(content)
    if not pem:
        return ProfileCertIssue(
            client_name=client_name,
            path=path,
            filename=filename,
            serial_hex=None,
            status="missing_cert",
        )
    serial_hex = cert_serial_hex_from_pem(pem)
    if not serial_hex:
        return ProfileCertIssue(
            client_name=client_name,
            path=path,
            filename=filename,
            serial_hex=None,
            status="unknown_serial",
        )
    status = serial_status(serial_hex, entries)
    if status == "R":
        return ProfileCertIssue(
            client_name=client_name,
            path=path,
            filename=filename,
            serial_hex=serial_hex,
            status="revoked",
        )
    if status == "E":
        return ProfileCertIssue(
            client_name=client_name,
            path=path,
            filename=filename,
            serial_hex=serial_hex,
            status="expired",
        )
    if status is None:
        return ProfileCertIssue(
            client_name=client_name,
            path=path,
            filename=filename,
            serial_hex=serial_hex,
            status="not_in_index",
        )
    not_after = cert_not_after_utc(pem)
    if not_after is not None and not_after <= now:
        return ProfileCertIssue(
            client_name=client_name,
            path=path,
            filename=filename,
            serial_hex=serial_hex,
            status="expired",
        )
    return None


def validate_client_profiles(
    adapter,
    client_name: str,
    *,
    index_entries: list[EasyRsaIndexEntry] | None = None,
    now: datetime | None = None,
) -> ProfileValidationResult:
    entries = index_entries if index_entries is not None else load_easyrsa_index(adapter)
    current = now or datetime.now(timezone.utc)
    issues: list[ProfileCertIssue] = []
    files = adapter.get_profile_files(client_name, VpnType.openvpn)
    for entry in files:
        path = entry.get("path") or ""
        filename = entry.get("filename") or Path(path).name
        if not path:
            continue
        try:
            content = adapter.read_profile_file(path)
        except Exception:
            continue
        issue = _issue_for_profile(
            client_name=client_name,
            path=path,
            filename=filename,
            content=content,
            entries=entries,
            now=current,
        )
        if issue is not None:
            issues.append(issue)
    return ProfileValidationResult(ready=not issues, issues=tuple(issues))


def validate_all_openvpn_profiles(
    adapter,
    client_names: list[str] | None = None,
    *,
    now: datetime | None = None,
) -> ProfileValidationResult:
    entries = load_easyrsa_index(adapter)
    if client_names is None:
        try:
            client_names = adapter.list_openvpn_clients()
        except Exception:
            client_names = []
    all_issues: list[ProfileCertIssue] = []
    for name in client_names:
        result = validate_client_profiles(
            adapter,
            name,
            index_entries=entries,
            now=now,
        )
        all_issues.extend(result.issues)
    return ProfileValidationResult(ready=not all_issues, issues=tuple(all_issues))


def clients_with_profile_issues(result: ProfileValidationResult) -> list[str]:
    return sorted({issue.client_name for issue in result.issues})


def profile_issues_payload(result: ProfileValidationResult) -> list[dict[str, str | None]]:
    return [
        {
            "client_name": issue.client_name,
            "path": issue.path,
            "filename": issue.filename,
            "serial_hex": issue.serial_hex,
            "status": issue.status,
        }
        for issue in result.issues
    ]
