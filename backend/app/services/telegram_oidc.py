"""Telegram Login via OpenID Connect (oauth.telegram.org)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from typing import Any

import httpx
from jose import jwt, jwk

OIDC_ISSUER = "https://oauth.telegram.org"
OIDC_AUTH_URL = f"{OIDC_ISSUER}/auth"
OIDC_TOKEN_URL = f"{OIDC_ISSUER}/token"
OIDC_JWKS_URL = f"{OIDC_ISSUER}/.well-known/jwks.json"
OIDC_SCOPE = "openid profile"
OIDC_STATE_TTL = 600

_oauth_store: dict[str, dict[str, Any]] = {}
_oauth_lock = threading.Lock()
_jwks_cache: dict[str, Any] | None = None
_jwks_cache_at: float = 0.0


def _cleanup_oauth_store() -> None:
    now = time.time()
    with _oauth_lock:
        stale = [k for k, v in _oauth_store.items() if now - v.get("created", 0) > OIDC_STATE_TTL]
        for key in stale:
            _oauth_store.pop(key, None)


def pkce_verifier() -> str:
    return secrets.token_urlsafe(32)[:64]


def pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def save_oidc_state(state: str, *, code_verifier: str, redirect_uri: str) -> None:
    _cleanup_oauth_store()
    with _oauth_lock:
        _oauth_store[state] = {
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "created": time.time(),
        }


def pop_oidc_state(state: str) -> dict[str, Any] | None:
    _cleanup_oauth_store()
    with _oauth_lock:
        return _oauth_store.pop(state, None)


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


def _get_jwks() -> dict[str, Any]:
    global _jwks_cache, _jwks_cache_at
    if _jwks_cache and time.time() - _jwks_cache_at < 3600:
        return _jwks_cache
    resp = httpx.get(OIDC_JWKS_URL, timeout=10.0)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_cache_at = time.time()
    return _jwks_cache


def _signing_key(id_token: str) -> Any:
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    alg = header.get("alg", "RS256")
    for jwk_dict in _get_jwks().get("keys", []):
        if jwk_dict.get("kid") == kid:
            return jwk.construct(jwk_dict), alg
    raise ValueError("Ключ подписи Telegram OIDC не найден")


def verify_id_token(id_token: str, *, client_id: str) -> dict[str, Any]:
    key, alg = _signing_key(id_token)
    return jwt.decode(
        id_token,
        key,
        algorithms=[alg],
        audience=client_id,
        issuer=OIDC_ISSUER,
    )


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
