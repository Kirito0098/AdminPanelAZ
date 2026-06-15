"""Client endpoint formatting and approximate IP geolocation."""

from __future__ import annotations

import ipaddress
import time
from pathlib import Path
from threading import Lock

import httpx

from app.config import get_settings

_PROTOCOL_PREFIXES = ("udp4:", "udp6:", "tcp4:", "tcp6:")
_GEO_CACHE_TTL_SECONDS = 86_400
_GEO_CACHE_MAX_ENTRIES = 2_000
_geo_cache: dict[str, tuple[float, dict[str, str | None]]] = {}
_geo_cache_lock = Lock()
_local_geo_initialized = False


def strip_protocol_prefix(address: str) -> str:
    addr = (address or "").strip()
    lower = addr.lower()
    for prefix in _PROTOCOL_PREFIXES:
        if lower.startswith(prefix):
            return addr[len(prefix) :].strip()
    return addr


def parse_client_endpoint(real_address: str | None) -> dict[str, str | None]:
    if not real_address or not real_address.strip():
        return {
            "client_ip": None,
            "port": None,
            "display_address": "—",
            "lookup_ip": None,
        }

    addr = strip_protocol_prefix(real_address)
    if addr.startswith("["):
        end = addr.find("]")
        if end != -1:
            client_ip = addr[: end + 1]
            lookup_ip = client_ip.strip("[]")
            rest = addr[end + 1 :].lstrip(":")
            port = rest if rest.isdigit() else None
            display_address = f"{client_ip}:{port}" if port else client_ip
            return {
                "client_ip": client_ip,
                "port": port,
                "display_address": display_address,
                "lookup_ip": lookup_ip,
            }

    host, _, maybe_port = addr.rpartition(":")
    if maybe_port.isdigit():
        return {
            "client_ip": host,
            "port": maybe_port,
            "display_address": f"{host}:{maybe_port}",
            "lookup_ip": host,
        }

    return {
        "client_ip": addr,
        "port": None,
        "display_address": addr,
        "lookup_ip": addr,
    }


def normalize_client_ip(real_address: str | None) -> str:
    parsed = parse_client_endpoint(real_address)
    return parsed["client_ip"] or parsed["lookup_ip"] or "неизвестно"


def _is_public_ip(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip.strip("[]"))
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


def _read_geo_cache(ip: str) -> dict[str, str | None] | None:
    with _geo_cache_lock:
        cached = _geo_cache.get(ip)
        if not cached:
            return None
        cached_at, payload = cached
        if time.time() - cached_at > _GEO_CACHE_TTL_SECONDS:
            _geo_cache.pop(ip, None)
            return None
        return payload


def _write_geo_cache(ip: str, payload: dict[str, str | None]) -> None:
    with _geo_cache_lock:
        if len(_geo_cache) >= _GEO_CACHE_MAX_ENTRIES:
            _geo_cache.clear()
        _geo_cache[ip] = (time.time(), payload)


def _empty_geo() -> dict[str, str | None]:
    return {
        "city": None,
        "country": None,
        "isp": None,
        "location_label": None,
        "geo_label": None,
    }


def build_geo_label(city: str | None, isp: str | None) -> str | None:
    parts = [part for part in (city, isp) if part]
    return " · ".join(parts) if parts else None


def _geo_from_api_item(item: dict) -> dict[str, str | None]:
    if item.get("status") != "success":
        return _empty_geo()
    city = (item.get("city") or "").strip() or None
    country = (item.get("country") or "").strip() or None
    isp = (item.get("isp") or item.get("org") or "").strip() or None
    location_parts = [part for part in (city, country) if part]
    location_label = ", ".join(location_parts) if location_parts else None
    return {
        "city": city,
        "country": country,
        "isp": isp,
        "location_label": location_label,
        "geo_label": build_geo_label(city, isp),
    }


def _ensure_local_geo_loaded() -> None:
    global _local_geo_initialized
    if _local_geo_initialized:
        return
    from app.services import geoip_local

    settings = get_settings()
    app_root = Path(__file__).resolve().parents[2]
    geoip_local.try_load_geoip_databases(
        Path(settings.geoip_city_mmdb_path),
        Path(settings.geoip_asn_mmdb_path) if settings.geoip_asn_mmdb_path else None,
        app_root=app_root,
    )
    _local_geo_initialized = True


def is_local_geoip_loaded() -> bool:
    _ensure_local_geo_loaded()
    from app.services import geoip_local

    return geoip_local.is_geoip_db_loaded()


def _lookup_local_geo(lookup_ip: str) -> dict[str, str | None] | None:
    _ensure_local_geo_loaded()
    from app.services import geoip_local

    if not geoip_local.is_geoip_db_loaded():
        return None
    return geoip_local.lookup_geo_local(lookup_ip)


def lookup_ip_geo(ip: str | None) -> dict[str, str | None]:
    lookup_ip = (ip or "").strip("[]")
    if not lookup_ip or not _is_public_ip(lookup_ip):
        return _empty_geo()

    cached = _read_geo_cache(lookup_ip)
    if cached is not None:
        return cached

    local_payload = _lookup_local_geo(lookup_ip)
    if local_payload is not None:
        _write_geo_cache(lookup_ip, local_payload)
        return local_payload

    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(
                f"http://ip-api.com/json/{lookup_ip}",
                params={"fields": "status,message,city,country,isp,org,query"},
            )
            response.raise_for_status()
            payload = _geo_from_api_item(response.json())
    except Exception:
        payload = _empty_geo()

    _write_geo_cache(lookup_ip, payload)
    return payload


def lookup_ips_geo(ips: list[str | None]) -> dict[str, dict[str, str | None]]:
    normalized_ips: list[str] = []
    seen: set[str] = set()
    for ip in ips:
        lookup_ip = (ip or "").strip("[]")
        if not lookup_ip or lookup_ip in seen or not _is_public_ip(lookup_ip):
            continue
        seen.add(lookup_ip)
        normalized_ips.append(lookup_ip)

    results: dict[str, dict[str, str | None]] = {}
    to_fetch: list[str] = []
    use_local_only = is_local_geoip_loaded()

    for lookup_ip in normalized_ips:
        cached = _read_geo_cache(lookup_ip)
        if cached is not None:
            results[lookup_ip] = cached
            continue
        if use_local_only:
            payload = _lookup_local_geo(lookup_ip) or _empty_geo()
            results[lookup_ip] = payload
            _write_geo_cache(lookup_ip, payload)
        else:
            to_fetch.append(lookup_ip)

    if to_fetch:
        batch_payload = [
            {"query": lookup_ip, "fields": "status,message,city,country,isp,org,query"}
            for lookup_ip in to_fetch[:100]
        ]
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.post("http://ip-api.com/batch", json=batch_payload)
                response.raise_for_status()
                for item in response.json():
                    lookup_ip = (item.get("query") or "").strip()
                    if not lookup_ip:
                        continue
                    payload = _geo_from_api_item(item)
                    results[lookup_ip] = payload
                    _write_geo_cache(lookup_ip, payload)
        except Exception:
            for lookup_ip in to_fetch:
                results[lookup_ip] = lookup_ip_geo(lookup_ip)

        for lookup_ip in to_fetch:
            results.setdefault(lookup_ip, _empty_geo())

    return results
