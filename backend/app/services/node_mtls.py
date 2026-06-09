"""mTLS configuration for panel ↔ node agent HTTP calls."""

from __future__ import annotations

import ssl
from pathlib import Path

from app.config import get_settings


def node_agent_mtls_enabled() -> bool:
    """Deprecated global flag; prefer per-node ``Node.mtls_enabled``."""
    settings = get_settings()
    return settings.node_agent_mtls_enabled


def build_node_agent_ssl_context(*, mtls_enabled: bool) -> ssl.SSLContext | bool | None:
    """Return SSL verify argument for httpx, or None if mTLS disabled for this node."""
    if not mtls_enabled:
        return None

    settings = get_settings()
    ca = Path(settings.node_agent_mtls_ca_cert)
    cert = Path(settings.node_agent_mtls_client_cert)
    key = Path(settings.node_agent_mtls_client_key)
    for path in (ca, cert, key):
        if not path.is_file():
            return None

    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.load_verify_locations(cafile=str(ca))
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def node_agent_base_scheme(*, mtls_enabled: bool) -> str:
    return "https" if mtls_enabled else "http"
