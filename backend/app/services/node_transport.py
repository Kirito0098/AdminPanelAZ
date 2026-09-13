"""Per-node transport registry (HTTP / mTLS; SSH stub for later)."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


TRANSPORT_HTTP = "http"
TRANSPORT_MTLS = "mtls"
TRANSPORT_SSH = "ssh"
SUPPORTED_WRITABLE = frozenset({TRANSPORT_HTTP, TRANSPORT_MTLS})
KNOWN_TRANSPORTS = frozenset({TRANSPORT_HTTP, TRANSPORT_MTLS, TRANSPORT_SSH})


@runtime_checkable
class NodeTransport(Protocol):
    id: str
    display_name: str
    is_tls: bool

    def base_scheme(self) -> str: ...

    def ssl_context(self) -> ssl.SSLContext | bool | None: ...


@dataclass(frozen=True)
class HttpTransport:
    id: str = TRANSPORT_HTTP
    display_name: str = "HTTP"
    is_tls: bool = False

    def base_scheme(self) -> str:
        return "http"

    def ssl_context(self) -> ssl.SSLContext | bool | None:
        return None


@dataclass(frozen=True)
class MtlsTransport:
    id: str = TRANSPORT_MTLS
    display_name: str = "HTTPS + mTLS"
    is_tls: bool = True

    def base_scheme(self) -> str:
        from app.services.node_mtls import node_agent_base_scheme

        return node_agent_base_scheme(mtls_enabled=True)

    def ssl_context(self) -> ssl.SSLContext | bool | None:
        from app.services.node_mtls import build_node_agent_ssl_context

        return build_node_agent_ssl_context(mtls_enabled=True)


@dataclass(frozen=True)
class SshTransport:
    """Stub — not available in P0."""

    id: str = TRANSPORT_SSH
    display_name: str = "SSH tunnel"
    is_tls: bool = False

    def base_scheme(self) -> str:
        raise NotImplementedError("SSH transport is not implemented")

    def ssl_context(self) -> ssl.SSLContext | bool | None:
        raise NotImplementedError("SSH transport is not implemented")


def list_transports() -> list[dict[str, Any]]:
    return [
        {"id": TRANSPORT_HTTP, "label": "HTTP", "available": True},
        {"id": TRANSPORT_MTLS, "label": "HTTPS + mTLS", "available": True},
        {"id": TRANSPORT_SSH, "label": "SSH tunnel", "available": False},
    ]


def resolve_transport_id(node: Any) -> str:
    """Single source of truth for a node's transport id (display + adapters)."""
    if bool(getattr(node, "is_local", False)):
        return TRANSPORT_HTTP
    raw = getattr(node, "transport", None)
    if isinstance(raw, str):
        raw = raw.strip().lower()
    else:
        raw = ""
    if raw in KNOWN_TRANSPORTS:
        return raw
    if not raw:
        # Legacy rows before/without transport column value
        return TRANSPORT_MTLS if bool(getattr(node, "mtls_enabled", False)) else TRANSPORT_HTTP
    raise ValueError(f"unsupported node transport: {raw}")


def sync_mtls_flag(node: Any) -> None:
    node.mtls_enabled = resolve_transport_id(node) == TRANSPORT_MTLS


def get_transport(node: Any) -> NodeTransport:
    tid = resolve_transport_id(node)
    if tid == TRANSPORT_HTTP:
        return HttpTransport()
    if tid == TRANSPORT_MTLS:
        return MtlsTransport()
    # Fail closed: ssh-in-DB and unknown values
    raise ValueError(f"unsupported node transport: {tid}")


def apply_transport_value(node: Any, transport: str) -> None:
    t = (transport or "").strip().lower()
    if t == TRANSPORT_SSH:
        raise ValueError("transport_not_implemented")
    if t not in SUPPORTED_WRITABLE:
        raise ValueError(f"unsupported transport: {t}")
    node.transport = t
    node.mtls_enabled = t == TRANSPORT_MTLS


def node_uses_tls(node: Any) -> bool:
    """Whether panel should speak TLS to this node (False for local / resolve errors)."""
    if bool(getattr(node, "is_local", False)):
        return False
    try:
        return get_transport(node).is_tls
    except ValueError:
        return False
