"""Local MaxMind GeoIP2/MMDB lookups (offline city/country/ISP)."""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

import geoip2.database
import geoip2.errors

logger = logging.getLogger(__name__)

_readers_lock = Lock()
_city_reader: geoip2.database.Reader | None = None
_asn_reader: geoip2.database.Reader | None = None
_loaded_city_path: str | None = None
_loaded_asn_path: str | None = None
_init_attempted = False


def _resolve_mmdb_path(path: Path, *, app_root: Path | None = None) -> Path:
    if path.is_absolute():
        return path
    if app_root is not None:
        return app_root / path
    return Path(__file__).resolve().parents[2] / path


def _close_readers() -> None:
    global _city_reader, _asn_reader, _loaded_city_path, _loaded_asn_path
    if _city_reader is not None:
        try:
            _city_reader.close()
        except Exception:
            pass
    if _asn_reader is not None:
        try:
            _asn_reader.close()
        except Exception:
            pass
    _city_reader = None
    _asn_reader = None
    _loaded_city_path = None
    _loaded_asn_path = None


def try_load_geoip_databases(
    city_path: Path,
    asn_path: Path | None = None,
    *,
    app_root: Path | None = None,
) -> bool:
    """Open MMDB readers when files exist. Returns True if city DB is loaded."""
    global _city_reader, _asn_reader, _loaded_city_path, _loaded_asn_path, _init_attempted

    resolved_city = _resolve_mmdb_path(city_path, app_root=app_root)
    resolved_asn = _resolve_mmdb_path(asn_path, app_root=app_root) if asn_path else None

    with _readers_lock:
        if (
            _city_reader is not None
            and _loaded_city_path == str(resolved_city)
            and _loaded_asn_path == (str(resolved_asn) if resolved_asn else None)
        ):
            return True

        _close_readers()
        _init_attempted = True

        if not resolved_city.is_file():
            logger.debug("GeoIP city MMDB not found: %s", resolved_city)
            return False

        try:
            _city_reader = geoip2.database.Reader(str(resolved_city))
            _loaded_city_path = str(resolved_city)
            logger.info("GeoIP city MMDB loaded: %s", resolved_city)
        except Exception as exc:
            logger.warning("GeoIP city MMDB load failed (%s): %s", resolved_city, exc)
            return False

        if resolved_asn and resolved_asn.is_file():
            try:
                _asn_reader = geoip2.database.Reader(str(resolved_asn))
                _loaded_asn_path = str(resolved_asn)
                logger.info("GeoIP ASN MMDB loaded: %s", resolved_asn)
            except Exception as exc:
                logger.warning("GeoIP ASN MMDB load failed (%s): %s", resolved_asn, exc)

        return True


def is_geoip_db_loaded() -> bool:
    with _readers_lock:
        return _city_reader is not None


def reset_geoip_readers() -> None:
    """Close readers and allow reload (tests)."""
    global _init_attempted
    with _readers_lock:
        _close_readers()
        _init_attempted = False


def lookup_geo_local(ip: str) -> dict[str, str | None] | None:
    """Lookup geo from local MMDB. Returns None when city DB is not loaded."""
    with _readers_lock:
        city_reader = _city_reader
        asn_reader = _asn_reader

    if city_reader is None:
        return None

    city = None
    country = None
    isp = None

    try:
        response = city_reader.city(ip)
        city = (response.city.name or "").strip() or None
        country = (response.country.name or "").strip() or None
    except geoip2.errors.AddressNotFoundError:
        pass
    except Exception as exc:
        logger.debug("GeoIP city lookup failed for %s: %s", ip, exc)

    if asn_reader is not None:
        try:
            asn_response = asn_reader.asn(ip)
            isp = (asn_response.autonomous_system_organization or "").strip() or None
        except geoip2.errors.AddressNotFoundError:
            pass
        except Exception as exc:
            logger.debug("GeoIP ASN lookup failed for %s: %s", ip, exc)

    location_parts = [part for part in (city, country) if part]
    location_label = ", ".join(location_parts) if location_parts else None
    label_parts = [part for part in (city, isp) if part]
    geo_label = " · ".join(label_parts) if label_parts else None
    return {
        "city": city,
        "country": country,
        "isp": isp,
        "location_label": location_label,
        "geo_label": geo_label,
    }
