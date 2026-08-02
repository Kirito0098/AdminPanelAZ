"""Best-effort conntrack → client mapping parse (no live net in unit tests)."""

from __future__ import annotations

import re
from typing import Any

# conntrack -L style (nf_conntrack):
# tcp 6 100 ESTABLISHED src=1.2.3.4 dst=5.6.7.8 sport=12345 dport=443 \
#   src=9.9.9.9 dst=5.6.7.8 sport=50443 dport=12345 [ASSURED] ...
_TUPLE_RE = re.compile(
    r"src=(?P<src>\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"dst=(?P<dst>\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"sport=(?P<sport>\d+)\s+"
    r"dport=(?P<dport>\d+)",
)


def parse_conntrack_mappings(text: str) -> list[dict[str, Any]]:
    """Parse conntrack -L output into mapping dicts.

    Shape: ``{ client_ip, client_port?, proxy_sport?, dest_ip?, dest_port? }``.
    """
    mappings: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tuples = list(_TUPLE_RE.finditer(line))
        if len(tuples) < 1:
            continue
        orig = tuples[0].groupdict()
        reply = tuples[1].groupdict() if len(tuples) > 1 else None
        client_ip = orig["src"]
        client_port = int(orig["sport"])
        dest_ip = None
        dest_port = None
        proxy_sport = None
        if reply:
            # For DNAT, reply src is usually the real destination
            dest_ip = reply["src"]
            dest_port = int(reply["sport"])
            proxy_sport = int(orig["dport"])
        key = (client_ip, client_port, dest_ip, dest_port, proxy_sport)
        if key in seen:
            continue
        seen.add(key)
        item: dict[str, Any] = {"client_ip": client_ip}
        item["client_port"] = client_port
        if proxy_sport is not None:
            item["proxy_sport"] = proxy_sport
        if dest_ip is not None:
            item["dest_ip"] = dest_ip
        if dest_port is not None:
            item["dest_port"] = dest_port
        mappings.append(item)
    return mappings
