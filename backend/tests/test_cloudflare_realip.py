import pytest
from app.services.cloudflare_realip import (
    content_hash,
    is_valid_origin_allow_conf,
    parse_cloudflare_ip_list,
    render_cloudflare_origin_allow_conf,
    render_cloudflare_realip_conf,
)


def test_parse_valid_lists():
    v4 = parse_cloudflare_ip_list("173.245.48.0/20\n104.16.0.0/13\n")
    assert "173.245.48.0/20" in v4
    v6 = parse_cloudflare_ip_list("2400:cb00::/32\n")
    assert v6 == ["2400:cb00::/32"]


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_cloudflare_ip_list("not-a-cidr\n")


def test_parse_rejects_empty():
    with pytest.raises(ValueError):
        parse_cloudflare_ip_list("\n# only comment\n")


def test_render_contains_snapshot_and_headers():
    body = render_cloudflare_realip_conf(
        ["173.245.48.0/20"],
        ["2400:cb00::/32"],
        snapshot_date="2026-08-20",
    )
    assert "# snapshot: 2026-08-20" in body
    assert "set_real_ip_from 173.245.48.0/20;" in body
    assert "set_real_ip_from 2400:cb00::/32;" in body
    assert "real_ip_header CF-Connecting-IP;" in body
    assert "real_ip_recursive on;" in body


def test_content_hash_stable():
    a = render_cloudflare_realip_conf(["173.245.48.0/20"], [], snapshot_date="2026-08-20")
    b = render_cloudflare_realip_conf(["173.245.48.0/20"], [], snapshot_date="2026-08-20")
    assert content_hash(a) == content_hash(b)


def test_render_origin_allow_contains_cf_localhost_rfc1918_deny():
    body = render_cloudflare_origin_allow_conf(
        ["173.245.48.0/20"],
        ["2400:cb00::/32"],
        snapshot_date="2026-09-14",
    )
    assert "# snapshot: 2026-09-14" in body
    assert "allow 173.245.48.0/20;" in body
    assert "allow 2400:cb00::/32;" in body
    assert "allow 127.0.0.1;" in body
    assert "allow ::1;" in body
    assert "allow 10.0.0.0/8;" in body
    assert "allow 172.16.0.0/12;" in body
    assert "allow 192.168.0.0/16;" in body
    assert body.strip().endswith("deny all;")


def test_is_valid_origin_allow_requires_cf_and_deny():
    good = render_cloudflare_origin_allow_conf(
        ["173.245.48.0/20"], [], snapshot_date="2026-09-14"
    )
    assert is_valid_origin_allow_conf(good) is True
    only_lan = "allow 10.0.0.0/8;\nallow 127.0.0.1;\ndeny all;\n"
    assert is_valid_origin_allow_conf(only_lan) is False
    assert is_valid_origin_allow_conf("") is False
