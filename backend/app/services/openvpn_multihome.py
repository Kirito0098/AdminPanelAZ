"""OpenVPN ``multihome`` patch for multi-IP servers.

AntiZapret stock server configs listen on ``0.0.0.0`` without ``multihome``, so
replies go out the primary address and clients on secondary IPs break. Desired
state lives in the panel DB; this module only inserts/removes a bare
``multihome`` directive in OpenVPN server confs. Restoration after AntiZapret
``setup.sh`` is done by the panel (toggle save / any panel doall), not by AZ hooks.
"""

from __future__ import annotations

import re
from typing import Any

OPENVPN_SERVER_CONF_NAMES: tuple[str, ...] = (
    "antizapret-udp.conf",
    "antizapret-tcp.conf",
    "vpn-udp.conf",
    "vpn-tcp.conf",
)

_PROTO_LINE_RE = re.compile(r"(?m)^proto\s+\S+.*$")
_BARE_MULTIHOME_RE = re.compile(r"(?m)^multihome[ \t]*\r?\n?")


def conf_has_bare_multihome(content: str) -> bool:
    """True if content has a non-comment bare ``multihome`` line."""
    return bool(_BARE_MULTIHOME_RE.search(content or ""))


def apply_multihome_to_conf(content: str, enabled: bool) -> str:
    """Insert or remove bare ``multihome`` after the first ``proto`` line (idempotent)."""
    text = content if content is not None else ""
    cleaned = _BARE_MULTIHOME_RE.sub("", text)
    if not enabled:
        return cleaned

    match = _PROTO_LINE_RE.search(cleaned)
    if match:
        insert_at = match.end()
        prefix = cleaned[:insert_at]
        suffix = cleaned[insert_at:]
        if not prefix.endswith("\n"):
            prefix += "\n"
        if suffix.startswith("\r\n"):
            suffix = suffix[2:]
        elif suffix.startswith("\n"):
            suffix = suffix[1:]
        return f"{prefix}multihome\n{suffix}"

    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned + "multihome\n"


def node_wants_openvpn_multihome(node: Any) -> bool:
    return bool(getattr(node, "openvpn_multihome", False))


def maybe_ensure_openvpn_multihome(adapter: Any, *, enabled: bool) -> dict[str, Any] | None:
    """Re-apply ``multihome`` on the node when the panel flag is on (after doall/restore)."""
    if not enabled:
        return None
    return adapter.ensure_openvpn_multihome(True)


def maybe_ensure_node_openvpn_multihome(adapter: Any, node: Any) -> dict[str, Any] | None:
    """Convenience: ensure when ``node.openvpn_multihome`` is true."""
    return maybe_ensure_openvpn_multihome(adapter, enabled=node_wants_openvpn_multihome(node))
