# openvpn_buffer_guard_parse.py
from __future__ import annotations
from dataclasses import dataclass
import re

ENOBUFS_NEEDLE = "No buffer space available"
_CLIENT_RE = re.compile(
    r"^(?P<cn>[^/\s]+)/(?:udp4|udp6|tcp4|tcp6):(?P<addr>[0-9a-fA-F.:]+):(?P<port>\d+)\s+.*No buffer space available"
)

@dataclass(frozen=True)
class EnobufsHit:
    common_name: str | None
    real_address: str | None

def parse_enobufs_line(line: str) -> EnobufsHit | None:
    if ENOBUFS_NEEDLE not in line:
        return None
    m = _CLIENT_RE.search(line.strip())
    if m:
        return EnobufsHit(m.group("cn"), f"{m.group('addr')}:{m.group('port')}")
    return EnobufsHit(None, None)

def summarize_enobufs(text: str) -> dict:
    by_cn: dict[str, int] = {}
    addr_for_cn: dict[str, str] = {}
    total = 0
    orphan = 0
    for line in text.splitlines():
        hit = parse_enobufs_line(line)
        if hit is None:
            continue
        total += 1
        if hit.common_name:
            by_cn[hit.common_name] = by_cn.get(hit.common_name, 0) + 1
            if hit.real_address:
                addr_for_cn[hit.common_name] = hit.real_address
        else:
            orphan += 1
    top_cn = max(by_cn, key=by_cn.get) if by_cn else None
    return {
        "total": total,
        "by_cn": by_cn,
        "top_cn": top_cn,
        "top_real_address": addr_for_cn.get(top_cn) if top_cn else None,
        "orphan_count": orphan,
    }
