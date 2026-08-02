"""Proxy NOC enrichment: match session endpoints to conntrack client IPs."""

from __future__ import annotations

import ipaddress
import logging
import time
from threading import Lock
from typing import Any, Callable

from app.services.ip_geo import parse_client_endpoint

logger = logging.getLogger(__name__)

PROXY_MAPPINGS_CACHE_TTL_SEC = 45

_cache_lock = Lock()
# node_id -> (expires_at_monotonic, mappings)
_mappings_cache: dict[int, tuple[float, list[dict[str, Any]]]] = {}


def clear_proxy_mappings_cache() -> None:
    with _cache_lock:
        _mappings_cache.clear()


def normalize_proxy_host(host: str) -> str | None:
    """Return normalized IPv4 literal, or None if not a usable IPv4 host."""
    value = (host or "").strip()
    if not value:
        return None
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return None
    if addr.version != 4:
        return None
    return str(addr)


def match_client_ip(
    endpoint: str | None,
    mappings: list[dict],
    proxy_ips: set[str],
) -> tuple[str | None, bool, bool]:
    """Match a VPN session endpoint against proxy IPs and sport mappings.

    Returns ``(resolved_ip_or_None, via_proxy, proxy_resolved)``.
    """
    parsed = parse_client_endpoint(endpoint)
    lookup_ip = parsed.get("lookup_ip")
    if not lookup_ip or lookup_ip not in proxy_ips:
        return None, False, False

    port_raw = parsed.get("port")
    if port_raw is None:
        return None, True, False

    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        return None, True, False

    for item in mappings or []:
        sport = item.get("proxy_sport")
        if sport is None:
            continue
        try:
            if int(sport) != port:
                continue
        except (TypeError, ValueError):
            continue
        client_ip = item.get("client_ip")
        if not client_ip:
            continue
        return str(client_ip), True, True

    return None, True, False


def get_mappings_for_proxy(
    adapter_factory: Callable[[int], Any],
    node_id: int,
    *,
    now: float | None = None,
) -> list[dict]:
    """Fetch proxy mappings with a process-local TTL cache (best-effort)."""
    ttl = PROXY_MAPPINGS_CACHE_TTL_SEC
    ts = time.monotonic() if now is None else now

    if ttl > 0:
        with _cache_lock:
            entry = _mappings_cache.get(node_id)
            if entry is not None and ts < entry[0]:
                return entry[1]

    mappings: list[dict] = []
    try:
        adapter = adapter_factory(node_id)
        payload = adapter.mappings()
        raw = payload.get("mappings") if isinstance(payload, dict) else None
        if isinstance(raw, list):
            mappings = [m for m in raw if isinstance(m, dict)]
    except Exception:
        logger.debug("proxy mappings fetch failed for node_id=%s", node_id, exc_info=True)
        mappings = []

    if ttl > 0:
        with _cache_lock:
            _mappings_cache[node_id] = (ts + ttl, mappings)
    return mappings
