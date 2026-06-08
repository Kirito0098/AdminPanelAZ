import subprocess

from app.services.openvpn_cert import cert_days_remaining_from_pem, extract_pem_from_ovpn

SAMPLE_OVPN = """client
dev tun
<cert>
-----BEGIN CERTIFICATE-----
MIIBszCCARugAwIBAgIQK7+8mGEfR8d3jQ0b0k5k1TANBgkqhkiG9w0BAQsFADAV
MRMwEQYDVQQDDAp0ZXN0LWNsaWVudDAeFw0yNTAxMDEwMDAwMDBaFw0yNjAxMDEw
MDAwMDBaMBUxEzARBgNVBAMMCnRlc3QtY2xpZW50MFwwDQYJKoZIhvcNAQEBBQAD
SwA3AQEAuFakeCertDataForUnitTestOnlyNotARealCertAtAll1234567890ab
cdEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/ab
cdEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/ab
cdEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/ab
cdEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/ab
cdEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/IwID
AQABo0IwYDALBgNVHQ8EBAMCAQYwEwYDVR0lBAwwCgYIKwYBBQUHAwIwEgYDVR0T
AQH/BAgwBgEB/wIBADAdBgNVHQ4EFgQUFakeFingerprintForTestOnlyNotReal
MA0GCSqGSIb3DQEBCwUAA0EAFakeSignatureDataForUnitTestOnlyNotReal==
-----END CERTIFICATE-----
</cert>
"""


def test_extract_pem_from_ovpn():
    pem = extract_pem_from_ovpn(SAMPLE_OVPN)
    assert pem is not None
    assert "BEGIN CERTIFICATE" in pem


def test_cert_days_remaining_from_pem_parses_openssl_enddate():
    result = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-nodes",
            "-days",
            "30",
            "-newkey",
            "rsa:2048",
            "-keyout",
            "/dev/null",
            "-out",
            "/dev/stdout",
            "-subj",
            "/CN=test-client",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    days = cert_days_remaining_from_pem(result.stdout)
    assert days is not None
    assert 25 <= days <= 30
