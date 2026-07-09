"""Restart all OpenVPN server instances after HA sync on a VPN node."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

OPENVPN_SERVER_UNITS: tuple[str, ...] = (
    "openvpn-server@antizapret-udp",
    "openvpn-server@antizapret-tcp",
    "openvpn-server@vpn-udp",
    "openvpn-server@vpn-tcp",
)

_SKIP_MARKERS = (
    "not found",
    "not loaded",
    "does not exist",
    "could not be found",
    "unit not found",
    "invalid argument",
)


def _should_skip_unit(error_text: str) -> bool:
    lowered = error_text.lower()
    return any(marker in lowered for marker in _SKIP_MARKERS)


def restart_all_openvpn_servers(adapter: Any) -> dict[str, Any]:
    """Restart every installed ``openvpn-server@*`` unit on the node."""
    restarted: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []

    for unit in OPENVPN_SERVER_UNITS:
        try:
            adapter.restart_service(unit)
            restarted.append(unit)
        except HTTPException as exc:
            detail = str(exc.detail or exc)
            if _should_skip_unit(detail):
                skipped.append(unit)
            else:
                logger.warning("OpenVPN restart failed on %s: %s", unit, detail)
                failed.append({"unit": unit, "error": detail})
        except Exception as exc:
            message = str(exc)
            if _should_skip_unit(message):
                skipped.append(unit)
            else:
                logger.warning("OpenVPN restart failed on %s: %s", unit, message)
                failed.append({"unit": unit, "error": message})

    return {
        "restarted": restarted,
        "skipped": skipped,
        "failed": failed,
        "success": not failed,
    }
