"""Agent JSON errors are operation failures, not TLS mismatches; TLS proxy pages keep their code."""

import httpx

from app.services.node_link_errors import (
    CODE_AUTH,
    CODE_ERROR,
    CODE_TLS_MISMATCH,
    classify_http_status,
    classify_request_error,
)

EASYRSA_DELETE_FAILURE = (
    "Ошибка AntiZapret: OpenVPN - Delete client 1231\n\n"
    "No Easy-RSA 'vars' configuration file exists!\n\n"
    "Using SSL:\n* openssl OpenSSL 3.0.13 30 Jan 2024 (Library: OpenSSL 3.0.13 30 Jan 2024)\n\n"
    "EasyRSA version 3.1.7\n\nError\n-----\n"
    "Cannot revoke this certificate, a conflicting file exists.\n"
    "* certificate: /etc/openvpn/easyrsa3/pki/revoked/certs_by_serial/C63509A369F02E6511D6B77514B44470.crt"
)


def test_agent_json_error_mentioning_ssl_is_not_a_tls_mismatch():
    code, message = classify_http_status(
        500, EASYRSA_DELETE_FAILURE, mtls_enabled=False, from_agent=True
    )

    assert code == CODE_ERROR
    assert "conflicting file exists" in message


def test_agent_error_text_is_not_mistaken_for_a_proxy_tls_page():
    code, message = classify_http_status(500, EASYRSA_DELETE_FAILURE, mtls_enabled=False)

    assert code == CODE_ERROR
    assert "conflicting file exists" in message


def test_tls_proxy_page_is_still_reported_as_a_tls_mismatch():
    code, message = classify_http_status(
        400, "400 The plain HTTP request was sent to HTTPS port", mtls_enabled=False
    )

    assert code == CODE_TLS_MISMATCH
    assert "mTLS" in message


def test_unauthorized_agent_response_is_an_auth_error():
    code, _ = classify_http_status(401, "bad key", mtls_enabled=True)

    assert code == CODE_AUTH


def test_ssl_transport_error_is_still_a_tls_mismatch():
    code, _ = classify_request_error(httpx.ConnectError("ssl: wrong version number"), mtls_enabled=False)

    assert code == CODE_TLS_MISMATCH
