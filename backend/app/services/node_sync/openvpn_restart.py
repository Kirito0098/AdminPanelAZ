"""Restart OpenVPN server instances, respecting setup protocol enable flags."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException

from app.services.antizapret_settings import is_vpn_monitor_service_expected

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


def _openvpn_active_units(adapter: Any) -> dict[str, bool] | None:
    """Return active flag per OpenVPN unit, or None if status could not be read."""
    try:
        statuses = adapter.get_service_status()
    except Exception as exc:
        logger.warning("OpenVPN restart: failed to read service status: %s", exc)
        return None
    return {
        svc.name: svc.active
        for svc in statuses
        if svc.name in OPENVPN_SERVER_UNITS
    }


def _protocol_flags_from_adapter(adapter: Any) -> dict[str, str] | None:
    """Best-effort OPENVPN_UDP/TCP_ENABLE (+ WIREGUARD) from node setup."""
    getter = getattr(adapter, "get_antizapret_settings", None)
    if not callable(getter):
        return None
    try:
        settings = getter() or {}
    except Exception as exc:
        logger.warning("OpenVPN restart: failed to read setup protocol flags: %s", exc)
        return None
    if not isinstance(settings, Mapping):
        return None
    return {
        key: str(settings.get(key, "y"))
        for key in ("OPENVPN_UDP_ENABLE", "OPENVPN_TCP_ENABLE", "WIREGUARD_ENABLE")
    }


def openvpn_units_allowed_by_setup(protocol_flags: Mapping[str, str] | None) -> list[str]:
    """Units allowed by OPENVPN_UDP_ENABLE / OPENVPN_TCP_ENABLE (default: all)."""
    if protocol_flags is None:
        return list(OPENVPN_SERVER_UNITS)
    return [
        unit
        for unit in OPENVPN_SERVER_UNITS
        if is_vpn_monitor_service_expected(unit, protocol_flags, default_enabled=True)
    ]


def restart_all_openvpn_servers(
    adapter: Any,
    *,
    protocol_flags: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Restart enabled/running ``openvpn-server@*`` units; skip disabled protocols.

    Skips units disabled in AntiZapret setup (``OPENVPN_TCP_ENABLE=n`` etc.) and,
    when systemd status is available, units that are not active.
    """
    restarted: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []

    flags = protocol_flags if protocol_flags is not None else _protocol_flags_from_adapter(adapter)
    allowed = set(openvpn_units_allowed_by_setup(flags))
    active_units = _openvpn_active_units(adapter)

    for unit in OPENVPN_SERVER_UNITS:
        if unit not in allowed:
            skipped.append(unit)
            continue
        # When status is known, only restart currently active instances.
        # When status is unknown, still restart only setup-enabled protocols
        # (do not touch TCP if OPENVPN_TCP_ENABLE=n).
        if active_units is not None and not active_units.get(unit, False):
            skipped.append(unit)
            continue
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
        "protocol_flags": dict(flags) if flags is not None else None,
    }
