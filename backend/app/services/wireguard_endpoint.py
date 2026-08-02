from __future__ import annotations

import re

_ENDPOINT_RE = re.compile(
    r"^(?P<prefix>\s*Endpoint\s*=\s*)(?P<value>\S+)(?P<suffix>\s*)$",
    re.IGNORECASE | re.MULTILINE,
)


def apply_wireguard_endpoint_host(content: str, host: str) -> str:
    host = (host or "").strip()
    if not host:
        return content

    def _sub(m: re.Match[str]) -> str:
        value = m.group("value")
        # host:port — take port after last ':' (IPv4/hostname only in our product)
        if ":" in value:
            port = value.rsplit(":", 1)[-1]
            if port.isdigit():
                return f"{m.group('prefix')}{host}:{port}{m.group('suffix')}"
        return f"{m.group('prefix')}{host}{m.group('suffix')}"

    new, n = _ENDPOINT_RE.subn(_sub, content, count=1)
    return new if n else content
