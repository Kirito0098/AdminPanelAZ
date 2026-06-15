"""Tests for client endpoint formatting and geo labels."""

from app.services.ip_geo import (
    build_geo_label,
    lookup_ip_geo,
    normalize_client_ip,
    parse_client_endpoint,
    strip_protocol_prefix,
)


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
