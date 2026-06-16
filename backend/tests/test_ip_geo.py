"""Tests for client endpoint formatting and geo labels."""

from unittest.mock import MagicMock, patch

import httpx

from app.services import geoip_local
from app.services.ip_geo import (
    _geo_cache,
    build_geo_label,
    get_geoip_status,
    is_local_geoip_loaded,
    lookup_ip_geo,
    lookup_ips_geo,
    normalize_client_ip,
    parse_client_endpoint,
    strip_protocol_prefix,
)


def setup_function():
    _geo_cache.clear()
    geoip_local.reset_geoip_readers()
    import app.services.ip_geo as ip_geo_module

    ip_geo_module._local_geo_initialized = False


def test_strip_protocol_prefix():
    assert strip_protocol_prefix("udp4:92.36.21.106:4744") == "92.36.21.106:4744"
    assert strip_protocol_prefix("tcp6:[2001:db8::1]:1194") == "[2001:db8::1]:1194"


def test_parse_client_endpoint_openvpn():
    parsed = parse_client_endpoint("udp4:92.36.21.106:4744")
    assert parsed["client_ip"] == "92.36.21.106"
    assert parsed["port"] == "4744"
    assert parsed["display_address"] == "92.36.21.106:4744"
    assert parsed["lookup_ip"] == "92.36.21.106"


def test_normalize_client_ip_strips_protocol_prefix():
    assert normalize_client_ip("udp4:92.36.21.106:4744") == "92.36.21.106"
    assert normalize_client_ip("203.0.113.10:51432") == "203.0.113.10"
    assert normalize_client_ip("[2001:db8::1]:1194") == "[2001:db8::1]"


def test_build_geo_label():
    assert build_geo_label("Moscow", "Rostelecom") == "Moscow · Rostelecom"
    assert build_geo_label(None, "Rostelecom") == "Rostelecom"


def test_lookup_ip_geo_private_ip():
    payload = lookup_ip_geo("10.8.0.5")
    assert payload["geo_label"] is None


def test_lookup_ip_geo_uses_local_db_without_http(tmp_path):
    local_payload = {
        "city": "Frankfurt",
        "country": "Germany",
        "isp": "Example ISP",
        "location_label": "Frankfurt, Germany",
        "geo_label": "Frankfurt · Example ISP",
    }

    with (
        patch("app.services.ip_geo._lookup_local_geo", return_value=local_payload),
        patch("app.services.ip_geo.is_local_geoip_loaded", return_value=True),
        patch("httpx.Client") as mock_client_cls,
    ):
        payload = lookup_ip_geo("8.8.8.8")

    assert payload == local_payload
    mock_client_cls.assert_not_called()


def test_lookup_ip_geo_falls_back_to_api_when_local_unavailable():
    api_response = MagicMock()
    api_response.json.return_value = {
        "status": "success",
        "city": "Ashburn",
        "country": "United States",
        "isp": "Google LLC",
        "query": "8.8.8.8",
    }
    api_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = api_response

    with (
        patch("app.services.ip_geo._lookup_local_geo", return_value=None),
        patch("app.services.ip_geo.is_local_geoip_loaded", return_value=False),
        patch("httpx.Client", return_value=mock_client),
    ):
        payload = lookup_ip_geo("8.8.8.8")

    assert payload["city"] == "Ashburn"
    assert payload["country"] == "United States"
    assert payload["geo_label"] == "Ashburn · Google LLC"
    mock_client.get.assert_called_once()


def test_lookup_ips_geo_batch_skips_http_when_local_loaded():
    local_payload = {
        "city": "Paris",
        "country": "France",
        "isp": None,
        "location_label": "Paris, France",
        "geo_label": "Paris",
    }

    with (
        patch("app.services.ip_geo.is_local_geoip_loaded", return_value=True),
        patch("app.services.ip_geo._lookup_local_geo", return_value=local_payload),
        patch("httpx.Client") as mock_client_cls,
    ):
        results = lookup_ips_geo(["1.1.1.1", "10.0.0.1", "1.1.1.1"])

    assert results["1.1.1.1"] == local_payload
    assert "10.0.0.1" not in results
    mock_client_cls.assert_not_called()


def test_is_local_geoip_loaded_false_without_mmdb_file():
    from app.config import Settings

    with patch("app.services.ip_geo.get_settings") as mock_settings:
        mock_settings.return_value = Settings(
            geoip_city_mmdb_path=__import__("pathlib").Path("data/geoip/missing.mmdb"),
            geoip_asn_mmdb_path=__import__("pathlib").Path("data/geoip/missing-asn.mmdb"),
        )
        assert is_local_geoip_loaded() is False


def test_get_geoip_status_reports_fallback_without_mmdb(tmp_path):
    from app.config import Settings

    city_path = tmp_path / "data" / "geoip" / "GeoLite2-City.mmdb"
    asn_path = tmp_path / "data" / "geoip" / "GeoLite2-ASN.mmdb"

    with patch("app.services.ip_geo.get_settings") as mock_settings:
        mock_settings.return_value = Settings(
            geoip_city_mmdb_path=city_path,
            geoip_asn_mmdb_path=asn_path,
        )
        status = get_geoip_status()

    assert status["loaded"] is False
    assert status["source"] == "ip-api"
    assert status["city_mmdb_exists"] is False
    assert status["asn_mmdb_exists"] is False
    assert str(city_path) == status["city_mmdb_path"]


def test_maintenance_geoip_status_endpoint(api_test_env):
    from fastapi.testclient import TestClient

    client = TestClient(api_test_env["app"])
    resp = client.get("/api/maintenance/geoip-status", headers=api_test_env["admin_headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["loaded"] is False
    assert body["source"] == "ip-api"
    assert "city_mmdb_path" in body
    assert body["city_mmdb_exists"] is False


def test_maintenance_geoip_status_requires_admin(api_test_env):
    from fastapi.testclient import TestClient

    client = TestClient(api_test_env["app"])
    resp = client.get("/api/maintenance/geoip-status", headers=api_test_env["viewer_headers"])
    assert resp.status_code == 403
