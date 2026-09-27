"""Telegram Login via OpenID Connect (oauth.telegram.org)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from datetime import timedelta
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.services.shared_state import pop_state, put_state

OIDC_ISSUER = "https://oauth.telegram.org"
OIDC_AUTH_URL = f"{OIDC_ISSUER}/auth"
OIDC_TOKEN_URL = f"{OIDC_ISSUER}/token"
OIDC_JWKS_URL = f"{OIDC_ISSUER}/.well-known/jwks.json"
OIDC_SCOPE = "openid profile"
OIDC_STATE_TTL = 600
OIDC_STATE_NAMESPACE = "tg_oidc_state"

_jwks_client: PyJWKClient | None = None
_jwks_client_lock = threading.Lock()


def pkce_verifier() -> str:
    return secrets.token_urlsafe(32)[:64]


def pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def save_oidc_state(state: str, *, code_verifier: str, redirect_uri: str) -> None:
    # The OAuth callback may reach another uvicorn worker.
    put_state(
        OIDC_STATE_NAMESPACE,
        state,
        {"code_verifier": code_verifier, "redirect_uri": redirect_uri},
        ttl=timedelta(seconds=OIDC_STATE_TTL),
    )


def pop_oidc_state(state: str) -> dict[str, Any] | None:
    return pop_state(OIDC_STATE_NAMESPACE, state)


def build_authorization_url(*, client_id: str, redirect_uri: str, state: str, code_verifier: str) -> str:
    from urllib.parse import urlencode

    save_oidc_state(state, code_verifier=code_verifier, redirect_uri=redirect_uri)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": OIDC_SCOPE,
            "state": state,
            "code_challenge": pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{OIDC_AUTH_URL}?{query}"


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    with _jwks_client_lock:
        if _jwks_client is None:
            # lifespan=3600 matches the previous 1h JWKS cache.
            _jwks_client = PyJWKClient(OIDC_JWKS_URL, cache_keys=True, lifespan=3600, timeout=10)
        return _jwks_client


def verify_id_token(id_token: str, *, client_id: str) -> dict[str, Any]:
    """Validate Telegram OIDC id_token; raise ValueError on any verify failure.

    Always pins ``algorithms=["RS256"]`` — never trusts the unverified header ``alg``.
    """
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(id_token)
        return jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=OIDC_ISSUER,
        )
    except jwt.PyJWKClientError as exc:
        raise ValueError("Ключ подписи Telegram OIDC не найден") from exc
    except jwt.PyJWTError as exc:
        raise ValueError("Недействительный Telegram OIDC id_token") from exc


def exchange_authorization_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    resp = httpx.post(
        OIDC_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
        },
        auth=(client_id, client_secret),
        timeout=15.0,
    )
    if resp.status_code >= 400:
        detail = resp.text.strip() or resp.reason_phrase
        raise ValueError(f"Telegram OIDC token exchange failed: {detail}")
    return resp.json()


def telegram_id_from_claims(claims: dict[str, Any]) -> str:
    raw = claims.get("id")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    sub = str(claims.get("sub", "")).strip()
    if sub:
        return sub
    raise ValueError("Telegram OIDC token не содержит id пользователя")
