"""Compare easyrsa3 archives: server identity changes and newly revoked clients."""

from __future__ import annotations

import hashlib
import io
import re
import tarfile
import zlib
from dataclasses import dataclass

SERVER_IDENTITY_MEMBERS: tuple[str, ...] = (
    "easyrsa3/pki/ca.crt",
    "easyrsa3/pki/issued/antizapret-server.crt",
    "easyrsa3/pki/private/antizapret-server.key",
)
_INDEX_MEMBER = "easyrsa3/pki/index.txt"
_CN_PATTERN = re.compile(r"/CN=([^/]+)")


@dataclass(frozen=True)
class PkiState:
    server_identity: dict[str, str]
    revoked: dict[str, str]
    valid_names: frozenset[str]


def _parse_index(text: str) -> tuple[dict[str, str], frozenset[str]]:
    revoked: dict[str, str] = {}
    valid: set[str] = set()
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) < 6:
            continue
        match = _CN_PATTERN.search(fields[5])
        if not match:
            continue
        name = match.group(1).strip()
        if fields[0] == "R":
            revoked[fields[3]] = name
        elif fields[0] == "V":
            valid.add(name)
    return revoked, frozenset(valid)


def read_pki_state(archive: object) -> PkiState | None:
    """Parse an ``export_easyrsa3_archive`` payload; ``None`` when it is not a readable archive."""
    if not isinstance(archive, (bytes, bytearray)):
        return None
    identity: dict[str, str] = {}
    index_text = ""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                name = member.name.removeprefix("./")
                if name not in SERVER_IDENTITY_MEMBERS and name != _INDEX_MEMBER:
                    continue
                handle = tar.extractfile(member)
                data = handle.read() if handle else b""
                if name == _INDEX_MEMBER:
                    index_text = data.decode("utf-8", errors="replace")
                else:
                    identity[name] = hashlib.sha256(data).hexdigest()
    except (tarfile.TarError, EOFError, zlib.error, OSError):
        return None
    revoked, valid_names = _parse_index(index_text)
    return PkiState(server_identity=identity, revoked=revoked, valid_names=valid_names)


def server_identity_changed(before: PkiState | None, after: PkiState | None) -> bool:
    """True unless both archives carry the same CA, server cert and server key."""
    if before is None or after is None:
        return True
    if len(after.server_identity) != len(SERVER_IDENTITY_MEMBERS):
        return True
    return before.server_identity != after.server_identity


def newly_revoked_clients(before: PkiState | None, after: PkiState | None) -> list[str]:
    """Clients revoked since ``before`` that have no valid certificate in ``after``."""
    if before is None or after is None:
        return []
    names = {name for serial, name in after.revoked.items() if serial not in before.revoked}
    return sorted(names - after.valid_names)
