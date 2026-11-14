"""Парсинг сертификатов OpenVPN через cryptography (без openssl subprocess)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.services.openvpn_cert import cert_not_after_utc
from app.services.openvpn_pki import cert_serial_hex_from_pem


def _make_cert(serial: int, not_after: datetime) -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "t")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_cert_serial_hex_from_pem_matches_openssl_format():
    # чётная длина hex — как есть.
    assert cert_serial_hex_from_pem(_make_cert(0xABC123, datetime(2036, 1, 1, tzinfo=timezone.utc))) == "ABC123"
    # нечётная длина дополняется нулём слева, как в выводе openssl (DER — чётное число байт).
    assert cert_serial_hex_from_pem(_make_cert(0xABC, datetime(2036, 1, 1, tzinfo=timezone.utc))) == "0ABC"


def test_cert_not_after_utc_parses():
    not_after = datetime(2036, 8, 13, 11, 49, 27, tzinfo=timezone.utc)
    assert cert_not_after_utc(_make_cert(1, not_after)) == not_after


def test_cert_parse_returns_none_on_bad_pem():
    assert cert_serial_hex_from_pem("not a cert") is None
    assert cert_not_after_utc("not a cert") is None
