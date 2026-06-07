"""mTLS configuration for panel ↔ node agent HTTP calls."""

from __future__ import annotations

import ssl
from pathlib import Path

from app.config import get_settings


def node_agent_mtls_enabled() -> bool:
    settings = get_settings()
    return settings.node_agent_mtls_enabled


def build_node_agent_ssl_context() -> ssl.SSLContext | bool | None:
    """Return SSL verify argument for httpx, or None if mTLS disabled."""
    settings = get_settings()
    if not settings.node_agent_mtls_enabled:
        return None

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


def node_agent_base_scheme() -> str:
    return "https" if node_agent_mtls_enabled() else "http"
