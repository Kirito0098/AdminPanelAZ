"""Short-TTL coalesce cache for local OpenVPN + WireGuard status probes.

Dashboard (and configs local-IP map) fan out multiple adapter reads within
seconds. RemoteNodeAdapter already reuses /monitoring/overview; the local
adapter previously re-parsed status logs on every call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable

from app.schemas import OpenVpnClient, WireGuardPeer

# Coalesce summary / overview / local-IP map within a dashboard load (~5–15s).
LOCAL_VPN_STATUS_TTL_SECONDS = 12.0

_lock = Lock()
_cache: tuple[float, "LocalVpnClientsSnapshot"] | None = None


@dataclass(frozen=True)
class LocalVpnClientsSnapshot:
    openvpn_clients: tuple[OpenVpnClient, ...]
    openvpn_data_source: str
    wireguard_peers: tuple[WireGuardPeer, ...]


def clear_local_vpn_status_cache() -> None:
    """Test helper — drop the local VPN clients snapshot cache."""
    global _cache
    with _lock:
        _cache = None


def get_local_vpn_clients_snapshot(
    fetcher: Callable[[], LocalVpnClientsSnapshot],
    *,
    ttl_seconds: float | None = LOCAL_VPN_STATUS_TTL_SECONDS,
) -> LocalVpnClientsSnapshot:
    """Return a cached local OVPN+WG snapshot, refreshing when TTL expires."""
    global _cache
    ttl = 0.0 if ttl_seconds is None else max(0.0, float(ttl_seconds))
    now = time.monotonic()
    if ttl > 0:
        with _lock:
            entry = _cache
            if entry is not None and now < entry[0]:
                return entry[1]

    snapshot = fetcher()
    if ttl > 0:
        with _lock:
            _cache = (time.monotonic() + ttl, snapshot)
    return snapshot
