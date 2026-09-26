"""Значения формы публикации попадают в .env и конфиг nginx: только безопасный формат."""

import pytest
from pydantic import ValidationError

from app.schemas import PortalPublishRequest, VpnNetworkPublishRequest


def _publish(**fields):
    return VpnNetworkPublishRequest(mode="uvicorn_custom", **fields)


@pytest.mark.parametrize(
    "domain",
    [
        "x.example.com\nFRONTEND_DIST_PATH=/",
        "x.example.com\n",
        "x.example.com\rSECRET_KEY=1",
        "x.example.com; location /leak { alias /etc/; }",
        "x.example.com|y",
        "x.example.com\\n",
        "x.example.com y.example.com",
        "-x.example.com",
        "x.example.com:99999",
        "x.example.com:port",
    ],
)
def test_publish_rejects_domain_that_could_inject_env_or_nginx(domain):
    with pytest.raises(ValidationError):
        _publish(domain=domain)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("panel.example.com", "panel.example.com"),
        ("  panel.example.com  ", "panel.example.com"),
        ("panel.example.com:8443", "panel.example.com:8443"),
        ("203.0.113.10", "203.0.113.10"),
        ("", None),
        (None, None),
    ],
)
def test_publish_accepts_hostname_ipv4_and_port(raw, expected):
    assert _publish(domain=raw).domain == expected


@pytest.mark.parametrize(
    "path",
    [
        "/etc/ssl/a.pem\nFRONTEND_DIST_PATH=/",
        "/etc/ssl/a.pem; include /etc/shadow",
        "etc/ssl/a.pem",
        "/etc/ssl/a b.pem",
        "/etc/ssl/{a}.pem",
    ],
)
@pytest.mark.parametrize("field", ["ssl_cert", "ssl_key"])
def test_publish_rejects_unsafe_certificate_paths(field, path):
    with pytest.raises(ValidationError):
        _publish(**{field: path})


def test_publish_accepts_letsencrypt_paths():
    req = _publish(
        ssl_cert="/etc/letsencrypt/live/panel.example.com/fullchain.pem",
        ssl_key="/etc/letsencrypt/live/panel.example.com/privkey.pem",
    )
    assert req.ssl_cert == "/etc/letsencrypt/live/panel.example.com/fullchain.pem"
    assert req.ssl_key == "/etc/letsencrypt/live/panel.example.com/privkey.pem"


@pytest.mark.parametrize("email", ["a@example.com\nX=1", "a b@example.com", "not-an-email", "a@example.com;"])
def test_publish_rejects_bad_email(email):
    with pytest.raises(ValidationError):
        _publish(email=email)


def test_publish_accepts_email():
    assert _publish(email=" admin@example.com ").email == "admin@example.com"


@pytest.mark.parametrize("domain", ["portal.example.com\nX=1", "portal.example.com; return 200"])
def test_publish_rejects_bad_portal_domain(domain):
    with pytest.raises(ValidationError):
        _publish(portal_domain=domain)


@pytest.mark.parametrize("domain", ["portal.example.com\nX=1", "portal.example.com; return 200"])
def test_portal_publish_rejects_bad_domain(domain):
    with pytest.raises(ValidationError):
        PortalPublishRequest(portal_domain=domain)


def test_portal_publish_rejects_bad_email():
    with pytest.raises(ValidationError):
        PortalPublishRequest(portal_domain="portal.example.com", email="a@example.com\nX=1")
