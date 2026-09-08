"""Telegram OIDC id_token verification (PyJWT)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services import telegram_oidc as oidc


@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _sign_id_token(private_key, *, client_id: str, exp_delta: timedelta, **extra_claims) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": oidc.OIDC_ISSUER,
        "aud": client_id,
        "sub": "12345",
        "id": 12345,
        "iat": now,
        "exp": now + exp_delta,
        **extra_claims,
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "test-kid"})


def _patch_signing_key(monkeypatch, public_key):
    signing = MagicMock()
    signing.key = public_key
    client = MagicMock()
    client.get_signing_key_from_jwt.return_value = signing
    monkeypatch.setattr(oidc, "_get_jwks_client", lambda: client)
    return client


def test_verify_id_token_happy_path(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    _patch_signing_key(monkeypatch, public_key)
    token = _sign_id_token(private_key, client_id="bot-client", exp_delta=timedelta(minutes=5))

    claims = oidc.verify_id_token(token, client_id="bot-client")

    assert claims["sub"] == "12345"
    assert str(claims["id"]) == "12345"


def test_verify_id_token_rejects_wrong_audience_as_value_error(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    _patch_signing_key(monkeypatch, public_key)
    token = _sign_id_token(private_key, client_id="bot-client", exp_delta=timedelta(minutes=5))

    with pytest.raises(ValueError):
        oidc.verify_id_token(token, client_id="other-client")


def test_verify_id_token_rejects_expired_as_value_error(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    _patch_signing_key(monkeypatch, public_key)
    token = _sign_id_token(private_key, client_id="bot-client", exp_delta=timedelta(minutes=-5))

    with pytest.raises(ValueError):
        oidc.verify_id_token(token, client_id="bot-client")


def test_verify_id_token_rejects_malformed_as_value_error(monkeypatch):
    _patch_signing_key(monkeypatch, MagicMock())

    with pytest.raises(ValueError):
        oidc.verify_id_token("not-a-jwt", client_id="bot-client")


def test_verify_id_token_pins_rs256_and_rejects_none_alg(monkeypatch, rsa_keypair):
    """Header alg must not be trusted — only RS256 is accepted."""
    _private_key, public_key = rsa_keypair
    _patch_signing_key(monkeypatch, public_key)
    # Forge a token with alg=none (unsigned). PyJWT should reject when algorithms pinned.
    header_payload = (
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."  # {"alg":"none","typ":"JWT"}
        "eyJpc3MiOiJodHRwczovL29hdXRoLnRlbGVncmFtLm9yZyIsImF1ZCI6ImJvdC1jbGllbnQiLCJzdWIiOiIxIn0."
    )

    with pytest.raises(ValueError):
        oidc.verify_id_token(header_payload, client_id="bot-client")


def test_verify_id_token_jwks_miss_is_value_error(monkeypatch):
    client = MagicMock()
    client.get_signing_key_from_jwt.side_effect = jwt.PyJWKClientError("no key")
    monkeypatch.setattr(oidc, "_get_jwks_client", lambda: client)
    # Valid-looking JWT structure so header parse succeeds
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _sign_id_token(private_key, client_id="bot-client", exp_delta=timedelta(minutes=5))

    with pytest.raises(ValueError, match="не найден"):
        oidc.verify_id_token(token, client_id="bot-client")
